from multiprocessing.sharedctypes import Value
import sys
import time
import logging
from itertools import islice

from .diff_tables import TableSegment, TableDiffer
from .database import connect_to_uri
from .parse_time import parse_time_before_now, UNITS_STR, ParseError

import click

LOG_FORMAT = "[%(asctime)s] %(levelname)s - %(message)s"
DATE_FORMAT = "%H:%M:%S"


@click.command()
@click.argument("db1_uri")
@click.argument("table1_name")
@click.argument("db2_uri")
@click.argument("table2_name")
@click.option("-k", "--key-column", default="id", help="Name of primary key column")
@click.option("-t", "--update-column", default=None, help="Name of updated_at/last_updated column")
@click.option("-c", "--columns", default=[], multiple=True, help="Names of extra columns to compare")
@click.option("-l", "--limit", default=None, help="Maximum number of differences to find")
@click.option("--bisection-factor", default=32, help="Segments per iteration")
@click.option("--bisection-threshold", default=1024**2, help="Minimal bisection threshold")
@click.option(
    "--min-age",
    default=None,
    help="Considers only rows older than specified. "
    "Example: --min-age=5min ignores rows from the last 5 minutes. "
    f"\nValid units: {UNITS_STR}",
)
@click.option("--max-age", default=None, help="Considers only rows younger than specified. See --min-age.")
@click.option("-s", "--stats", is_flag=True, help="Print stats instead of a detailed diff")
@click.option("-d", "--debug", is_flag=True, help="Print debug info")
@click.option("-v", "--verbose", is_flag=True, help="Print extra info")
def main(
    db1_uri,
    table1_name,
    db2_uri,
    table2_name,
    key_column,
    update_column,
    columns,
    limit,
    bisection_factor,
    bisection_threshold,
    min_age,
    max_age,
    stats,
    debug,
    verbose,
):
    if limit and stats:
        print("Error: cannot specify a limit when using the -s/--stats switch")
        return

    if debug:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, datefmt=DATE_FORMAT)
    elif verbose:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=DATE_FORMAT)

    db1 = connect_to_uri(db1_uri)
    db2 = connect_to_uri(db2_uri)

    start = time.time()

    try:
        options = dict(
            min_time=min_age and parse_time_before_now(min_age), max_time=max_age and parse_time_before_now(max_age)
        )
    except ParseError as e:
        logging.error("Error while parsing age expression: %s" % e)
        return

    table1 = TableSegment(db1, (table1_name,), key_column, update_column, columns, **options)
    table2 = TableSegment(db2, (table2_name,), key_column, update_column, columns, **options)

    differ = TableDiffer(bisection_factor=bisection_factor, bisection_threshold=bisection_threshold, debug=debug)
    diff_iter = differ.diff_tables(table1, table2)

    if limit:
        diff_iter = islice(diff_iter, int(limit))

    if stats:
        diff = list(diff_iter)
        percent = 100 * len(diff) / table1.count
        print(f"Diff-Total: {len(diff)} changed rows out of {table1.count}")
        print(f"Diff-Percent: {percent:.4f}%")
        plus = len([1 for op, _ in diff if op == "+"])
        minus = len([1 for op, _ in diff if op == "-"])
        print(f"Diff-Split: +{plus}  -{minus}")
    else:
        for op, key in diff_iter:
            print(op, key)
            sys.stdout.flush()

    end = time.time()

    logging.info(f"Duration: {end-start:.2f} seconds.")


if __name__ == "__main__":
    main()