import re
import pdfplumber
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta
from db_manager import Transaction, AccountType

overrideDuplicates = True  # True = assume all 'duplicate' transactions are valid

regexes = {
    "DEBIT": {
        "txn_groups": [
            "dates",
            "description2",
            "category",
            "description",
            "amount",
            "closing",
            "",
            "",
            "",
        ],
        "txn": (
            r"^(?P<dates>(?:\w{3}(\.|)) \d{2}) "
            r"((?:INTERAC)|(?:Plus Plan)|(?:Other Bank)|(?:ABM)|(?:Mobile)|(?:.*,)) (?P<description>.+)\s"
            r"(?P<amount>-?[\d,]+\.\d{2}) (?P<closing>-?[\d,]+\.\d{2})"
            r"\n((?!(?:\w{3}(\.|)) \d{2})(?!continued)(?P<description2>.*))?"
        ),
        "startyear": r"For the period ending\s\w+\.?\s{1}\d+\,\s{1}(?P<year>[0-9]{4})",
        "openbal": r"Opening balance (?P<balance>[\d,]+\.\d{2})",
        "closingbal": r"# \d{4} [\d]{4}-\d{3} (?:[\d,]+\.\d{2}) (?:[\d,]+\.\d{2}) (?:[\d,]+\.\d{2}) (?P<balance>[\d,]+\.\d{2})",
    },
    "CREDIT": {
        "txn": (
            r"^(?P<dates>(?:\w{3}(\.|)+ \d{1,2}\s*){2})"
            r"(?P<description>.+)\s"
            r"(?P<amount>-?[\d,]+\.\d{2})(?P<cr>(\-|\s*CR))?"
        ),
        "startyear": r"Statement Date\s\w+\.?\s{1}\d+\,\s{1}(?P<year>[0-9]{4})",
        "openbal": r"Previous (?:total )*[bB]alance[\., \s\w\d]*(?P<balance>-?\$[\d,]+\.\d{2})(?P<cr>(\-|\s?CR))?",
        "closingbal": r"((?:Total)|(?:New)) [b|B]alance\s.*(?P<balance>-?\$[\d,]+\.\d{2})(?P<cr>(\-|\s?CR))?",
    },
}


def get_transactions(data_directory, target_fi, debug=False):
    result = []
    for pdf_path in Path(data_directory).rglob("*.pdf"):
        if pdf_path.parts[-2] == target_fi:
            result += _parse_pdf(pdf_path, target_fi, debug)
    return result


def _parse_pdf(pdf_path, target_fi, debug=False):
    result = []
    text = ""

    with pdfplumber.open(pdf_path) as pdf:
        print("------------------------------------------")
        print(pdf_path)
        for page in pdf.pages:
            text += page.extract_text(x_tolerance=1)

        year = _get_start_year(text, target_fi)
        opening_bal = _get_opening_bal(text, target_fi)
        closing_bal = _get_closing_bal(text, target_fi)
        current_bal = opening_bal

        txt_path = str(pdf_path).replace(".pdf", ".txt")
        with open(txt_path, "w") as f:
            f.write(text)

        file_name = str(pdf_path).split("/")[-1]
        file_year = file_name.split(" ")[-1].split(".")[0]
        file_month = file_name.split(" ")[0]
        file_date = datetime.strptime(file_month + " " + file_year, "%B %Y")

        # debugging transaction mapping - all 3 regex in 'txn' have to find a result in order for it to be considered a 'match'
        for match in re.findall(regexes[target_fi]["txn"], text, re.MULTILINE):
            match_dict = dict(zip(regexes[target_fi]["txn_groups"], match))

            date = get_date(match_dict["dates"], year, file_date)
            description = match_dict["description"]
            amount = float(match_dict["amount"].replace("$", "").replace(",", ""))
            category = match_dict.get("category")

            if match_dict.get("cr"):
                print("Credit found in transaction: '%s'" % match_dict["amount"])
            if match_dict.get("closing"):
                closing_bal = float(
                    match_dict["closing"].replace("$", "").replace(",", "")
                )
                if round(current_bal - amount, 2) == round(closing_bal, 2):
                    amount = -amount
                elif round(current_bal + amount, 2) == round(closing_bal, 2):
                    amount = abs(amount)
                else:
                    breakpoint()
                current_bal = closing_bal
            else:
                amount = -amount

            if match_dict.get("description2"):
                description += match_dict["description2"]

            transaction = Transaction(
                AccountType[target_fi],
                category,
                str(date.date().isoformat()),
                description.strip(","),
                amount,
            )
            result.append(transaction)

    _validate(closing_bal, opening_bal, result, target_fi)

    csv_path = str(pdf_path).replace(".pdf", ".csv")

    with open(csv_path, "w") as f:
        f.write("Date,Description,Amount\n")
        for t in sorted(list(result), key=lambda t: t.date):
            f.write(f"{t.date},{t.description},{t.amount}\n")

    return result


def get_date(date_str, year, file_date):
    date = date_str.replace("/", " ")  # change format to standard: 03/13 -> 03 13
    date = date.split(" ")[0:2]  # Aug. 10 Aug. 13 -> ['Aug.', '10']
    date[0] = date[0].strip(".")  # Aug. -> Aug
    date.append(str(year))
    date = " ".join(date)  # ['Aug', '10', '2021'] -> Aug 10 2021

    try:
        date = datetime.strptime(date, "%b %d %Y")  # try Aug 10 2021 first
    except:  # yes I know this is horrible, but this script runs once if you download your .csvs monthly, what do you want from me
        date = datetime.strptime(date, "%m %d %Y")  # if it fails, 08 10 2021

    # need to account for current year (Jan) and previous year (Dec) in statements
    endOfYearCheck = date.strftime("%m")

    if endOfYearCheck == "12" and file_date.strftime("%m") == "01":
        date = date - relativedelta(years=1)

    return date


def _validate(closing_bal, opening_bal, transactions, target_fi):
    # spend transactions are negative numbers.
    # net will most likely be a neg number unless your payments + cash back are bigger than spend
    # outflow is less than zero, so purchases
    # inflow is greater than zero, so payments/cashback

    # closing balance is a positive number
    # opening balance is only negative if you have a CR, otherwise also positive
    net = round(sum([r.amount for r in transactions]), 2)
    outflow = round(sum([r.amount for r in transactions if r.amount < 0]), 2)
    inflow = round(sum([r.amount for r in transactions if r.amount > 0]), 2)
    if round(opening_bal - closing_bal, 2) != net and (
        abs(round(opening_bal - closing_bal, 2)) != abs(net)
        or "DEBIT" != target_fi
    ):
        print("* the diff is: %f vs. %f" % (opening_bal - closing_bal, net))
        print(f"* Opening reported at {opening_bal}")
        print(f"* Closing reported at {closing_bal}")
        print(f"* Transactions (net/inflow/outflow): {net} / {inflow} / {outflow}")
        print("* Parsed transactions:")
        for t in transactions:
            print(f"  {t.date} {t.description} {t.amount}")
        raise AssertionError(
            "Discrepancy found, bad parse :(. Not all transactions are accounted for, validate your transaction regex."
        )


def _get_start_year(pdf_text, fi):
    print("Getting year...")
    match = re.search(regexes[fi]["startyear"], pdf_text, re.IGNORECASE)
    year = int(match.groupdict()["year"].replace(", ", ""))
    print("YEAR IS: %d" % year)
    return year


def _get_opening_bal(pdf_text, fi):
    print("Getting opening balance...")
    match = re.search(regexes[fi]["openbal"], pdf_text)
    if match.groupdict().get("cr") and "-" not in match.groupdict()["balance"]:
        balance = float("-" + match.groupdict()["balance"].replace("$", ""))
        print("Patched credit balance found for opening balance: %f" % balance)
        return balance

    balance = float(match.groupdict()["balance"].replace(",", "").replace("$", ""))
    print("Opening balance: %f" % balance)
    return balance


def _get_closing_bal(pdf_text, fi):
    print("Getting closing balance...")
    match = re.search(regexes[fi]["closingbal"], pdf_text)
    if match.groupdict().get("cr") and "-" not in match.groupdict()["balance"]:
        balance = float("-" + match.groupdict()["balance"].replace("$", ""))
        print("Patched credit balance found for closing balance: %f" % balance)
        return balance

    balance = float(
        match.groupdict()["balance"].replace(",", "").replace("$", "").replace(" ", "")
    )
    print("Closing balance: %f" % balance)
    return balance
