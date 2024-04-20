from enum import Enum

class AccountType(Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class Transaction:
    def __init__(self, account_type, transaction_type, date, description, amount):
        self.account_type = account_type
        self.transaction_type = transaction_type
        self.date = date
        self.description = description
        self.amount = amount

    def __hash__(self):
        return hash(
            (
                self.account_type,
                self.transaction_type,
                self.date,
                self.description,
                self.amount,
            )
        )

    def __eq__(self, other):
        return (
            isinstance(other, Transaction)
            and self.account_type == other.account_type
            and self.transaction_type == other.transaction_type
            and self.date == other.date
            and self.description == other.description
            and self.amount == other.amount
        )

    def __repr__(self):
        return f"  {self.date} {self.transaction_type} {self.description} {self.amount}"


def create_db(db_conn):
    db_conn.execute(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            account_type varchar(255),
            transaction_type varchar(255),
            timestamp varchar(255),
            description varchar(255),
            amount REAL
        )
        """
    )


def add_to_db(db_conn, transactions):
    for t in transactions:
        db_conn.execute(
            """
            INSERT INTO transactions
            (account_type, transaction_type, timestamp, description, amount)
            VALUES
            (?, ?, ?, ?, ?)
            """,
            [t.account_type.value, t.transaction_type, t.date, t.description, t.amount],
        )


def get_existing_trans(db_conn):
    existing_rows = db_conn.execute(
        """
        SELECT account_type,
               transaction_type,
               timestamp,
               description,
               amount
        FROM transactions
        """
    ).fetchall()

    existing_trans = [
        Transaction(AccountType(e[0]), e[1], e[2], e[3], e[4]) for e in existing_rows
    ]
    return existing_trans
