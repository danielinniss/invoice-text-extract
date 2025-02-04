import os
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import sleep

import botocore
from rich import print
from rich.console import Console

import boto3
import typer
from rich.panel import Panel
from rich.pretty import Pretty
from typing_extensions import TypedDict
import base64
import requests

err_console = Console(stderr=True)
base = Path(__file__).parent.resolve()
AWS_PROFILE = "hokodo_dev"
AWS_REGION = "eu-west-2"

app = typer.Typer()


@app.command()
def aws(path: str = None):
    _aws(path)


@app.command()
def docupanda(path: str = None):
    check_path(path)

    _docupanda(path)


url = "https://app.docupanda.io/document"
docupanda_api_key = os.environ.get("DOCUPANDA_API_KEY", "")
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "X-API-Key": docupanda_api_key
}


def _docupanda(path):

    with open(path, "rb") as f:
        payload = {"document": {"file": {
            "contents": base64.b64encode(f.read()).decode(),
            "filename": "example_document.pdf"
        }}}

    response = requests.post(url, json=payload, headers=headers)
    document_id = response.json()['documentId']

    status = ""
    retries = 0
    sleep(5)
    while status != "completed":
        response = requests.get(f"{url}/{document_id}", headers=headers)
        status = response.json()["status"]

        sleep_ = math.pow(2, retries) - 1
        print(f">> [yellow]{status}: Retrying in {sleep_} seconds.[/yellow]")

        if retries == 5:
            print("Retries exceeded")
            break

        retries += 1
        sleep(sleep_)
    else:
        print(response.json())


class Invoice(TypedDict, total=False):
    number: str = ""
    amount: Decimal = ""
    currency: str = ""


def _aws(path: str = None) -> None:
    check_path(path)

    payload = get_file_document_payload(path)
    invoice = extract_invoice_info_with_analyze_expense(payload)

    print(
        Panel(
            Pretty(invoice, expand_all=True),
            title=f"[cyan]Invoice Number: [bold]{invoice['number']}[/bold][/cyan]", subtitle="Thank You", title_align="left", subtitle_align="right")
    )


def get_file_document_payload(document_path):
    # Read the document file
    with open(document_path, 'rb') as document:
        return bytearray(document.read())


def extract_invoice_info_with_analyze_expense(file_bytes: bytearray) -> dict:
    # you'll need an aws 'credentials' file in you home directory e.g /home/daniel/.aws/credentials
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    textract = session.client('textract')

    try:
        # Call the AnalyzeExpense API
        response = textract.analyze_expense(Document={'Bytes': file_bytes})
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == "AnalyzeExpenseRequestError":
            raise Exception(f"AnalyzeExpenseRequestError: {error}")

        raise error

    invoice = Invoice(number="Not Found", amount=0, currency="")

    # Iterate through the expense documents
    for expense_doc in response['ExpenseDocuments']:
        for summary_field in expense_doc['SummaryFields']:
            if summary_field["Type"].get("Text") == "INVOICE_RECEIPT_ID":
                invoice["number"] = summary_field["ValueDetection"]["Text"]
            if summary_field["Type"].get("Text") == "AMOUNT_DUE":
                invoice["amount"] = strip(summary_field['ValueDetection']['Text'])
                invoice["currency"] = summary_field.get("Currency")

    return invoice


number_match = re.compile(r"([\d+,.])+")


def strip(number):
    if matches := number_match.match(number):
        try:
            number = Decimal(matches.group(0).replace(",", "."))
        except InvalidOperation:
            pass
    return number


def check_path(path):
    try:
        path = base / Path(path)

        if not path.exists():
            err_console.print(f"{path} does not exist!")
            raise typer.Exit(code=1)
    except TypeError:
        err_console.print(f"\n{path} [red]is not a valid path![/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
