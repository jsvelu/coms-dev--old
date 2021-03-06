from newage.utils import ExportCSVMixin


class ExportCSVForOrdersQuotes(ExportCSVMixin):

    exclude_columns = ()
    extra_columns = []

    def get_extra_columns_per_record(self, record):
        return[]

    def get_exclude_cols(self):
        return self.exclude_columns

    def get_extra_cols(self):
        return self.extra_columns

    def get_headers(self, table=None):
        if not table:
            return None
        return [col.verbose_name for col in table.columns if col.name not in self.get_exclude_cols()] + self.get_extra_cols()

    def get_rows(self, table=None):
        if not table:
            return None

        rows = [
            [
                str(value)
                for column, value in list(row.items())
                if column.name not in self.get_exclude_cols()
            ] +
            self.get_extra_columns_per_record(row.record)

            for row in table.rows
            ]
        return rows


'''
# TODO: This appears not to be used
class OrdersUtil():

    @staticmethod
    def get_order_type(order):
        if order.customer is not None:
            order_for = order.customer.first_name + ' ' + order.customer.last_name
            order_type = "Customer"
        else:
            order_for = order.dealership.name
            order_type = "Dealership"

        order_target = {"for": order_for, "type": order_type}
        return order_target
'''
