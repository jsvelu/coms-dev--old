import csv
from datetime import date
from datetime import datetime

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from django.db.utils import DatabaseError
from django.utils import timezone

from orders.models import Order
from orders.models import OrderDocument
from production.models import Build

NULL_DATES = (
    '1/1/00',
    '12/31/99',
    '',
)


DATE_WHEN_NULL = date(2000, 1, 1)


def _parse_date(date_str):
    if date_str in NULL_DATES:
        return DATE_WHEN_NULL

    return datetime.strptime(date_str, '%m/%d/%y').replace(tzinfo=timezone.get_current_timezone())


class Command(BaseCommand):
    help = 'Update the delivery details of orders as per given spreasheet.'

    def add_arguments(self, parser):

        parser.add_argument('--csv',
            action='store',
            dest='csv_filename',
            help='The CSV input file.')

        parser.add_argument('--commit',
            action='store_true',
            dest='commit',
            help='Without this flag, the command makes the verification of the data validity but does not update the database.')

    def handle(self, *args, **options):
        csv_filename = options.get('csv_filename')
        commit = options.get('commit')

        verb = 'Updating' if commit else 'Checking'

        if not csv:
            raise CommandError('Please provide csv file (--csv)')

        with open(csv_filename, 'rb') as csv_input:
            reader = csv.reader(csv_input)

            try:
                with transaction.atomic():
                    for row in list(reader)[1:]:
                        chassis = row[1]

                        order = Order.objects.filter(chassis=chassis).first()

                        if not order:
                            raise Exception('Order with chassis {} does not exist.'.format(chassis))

                        print(verb + ' Order {}'.format(order))

                        build = Build.objects.filter(order__chassis=chassis).first()

                        build.vin_number = row[2]
                        build.weight_tare = row[4]
                        build.weight_atm = row[5]
                        build.weight_tow_ball = row[7]
                        build.weight_tyres = row[8]
                        build.weight_chassis_gtm = row[9]
                        build.weight_gas_comp = row[10]
                        build.weight_payload = row[11]
                        build.qc_date_planned = _parse_date(row[12])
                        build.qc_date_actual = _parse_date(row[13])
                        build.save()

                        order.dispatch_date_planned = _parse_date(row[14])
                        order.dispatch_date_actual = _parse_date(row[15])
                        order.received_date_dealership = _parse_date(row[17])
                        order.delivery_date_customer = _parse_date(row[19])
                        order.save()

                        order.orderdocument_set.create(
                            type=OrderDocument.DOCUMENT_HANDOVER_TO_DRIVER_FORM,
                            is_separated=True,
                        )
                        order.orderdocument_set.create(
                            type=OrderDocument.DOCUMENT_HANDOVER_TO_DEALERSHIP_FORM,
                            is_separated=True,
                        )

                    if not commit:
                        raise DatabaseError()

                print('Database has been successfully updated.')

            except DatabaseError:
                print('Data is valid, not change has been made to the database. Please use argument --commit.')
