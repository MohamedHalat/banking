import os
import sqlite3
import click
import pdf_processor
import db_manager

@click.command()
@click.argument("database")
@click.option("-d", "directory", required=False, default='statement')
@click.option("--fi", "target_fi", required=False, default="CREDIT")
@click.option("--debug", is_flag=True)
def main(
    database: str, directory: str, target_fi: str, debug: bool
):
    """
    Given a directory of pdf statements, parse the statements and add the transactions to the database.

    Example usage:
    python teller.py database.db --fi credit --debug

    :param database: The path to the sqlite3 database file
    :param directory: The directory containing the pdf statements
    :param target_fi: The financial institution of the pdf statements
    :param debug: Print debug information

    :return: None
    """
    if not os.path.exists(directory):
        print(f"Directory '{directory}' does not exist")
        return

    with sqlite3.connect(database) as db_conn:
        try:
            db_manager.create_db(db_conn)
        except sqlite3.OperationalError:  # db exists
            pass

        print(f"Searching for pdfs in '{directory}'...")
        found_trans = pdf_processor.get_transactions(directory, target_fi.upper(), debug=debug)
        print(f"Found {len(found_trans)} transactions in pdf statements")

        print(f"Adding {len(found_trans)} new transactions to db...")
        db_manager.add_to_db(db_conn, found_trans)


if __name__ == "__main__":
    main()
