

import os
import openpyxl
import json
import csv
import itertools
import calendar
import datetime

import collections
from datetime import datetime
from decimal import Decimal
from itertools import chain
from itertools import groupby
from operator import itemgetter
from copy import copy
from collections import OrderedDict 
import functools


from django.db.models   import Count
from django.db.models   import Sum
from django.db.models   import Q
from django.db import connection
from django.db.models import Count, Case, When, IntegerField
from django.conf import settings
from django.utils import timezone
from django.views.generic.base import TemplateView
from django.http.response import HttpResponse
from django.shortcuts import render
from django.shortcuts import render_to_response
from django.views.generic.base import View
from rest_framework.generics import get_object_or_404
from rules.contrib.views import PermissionRequiredMixin

from caravans.models import SeriesSKU
from dealerships.models import Dealership
from newage.utils import ExportCSVMixin
from orders.models import Order
from orders.models import OrderSKU
from orders.models import Show
from caravans.models import Model
from caravans.models import Series
from schedule.models import MonthPlanning

from .rules import get_user_mps_dealerships


SECONDS_PER_DAY = 24*60*60
SELECTIONS_DAYS_UNRESOLVED = 7
SALESREPORT_DEALERSHIP_ID_ALL = -1



def get_status(order):
    if order.order_cancelled is not None:
        return 'Cancelled'

    if order.get_finalization_status() != Order.STATUS_APPROVED:
        return 'Pending'

    customer_approval_status = order.get_customer_plan_status()

    if customer_approval_status in (Order.STATUS_NONE, Order.STATUS_REJECTED):
        return 'Drafting'

    if customer_approval_status == Order.STATUS_PENDING:
        return 'Signoff'

    if customer_approval_status == Order.STATUS_APPROVED:
        return 'Ready'

    return 'Unknown'

class MpsIndexView(PermissionRequiredMixin, TemplateView):
    template_name = 'mps/index.html'
    permission_required = 'mps.view_mps_page'

    def get_context_data(self, **kwargs):
        data = super(MpsIndexView, self).get_context_data(**kwargs)
        data['shows'] = [
            {
                'id': show.id,
                'name': show.name,
            }
            for show in Show.objects.all()
        ]

        data['models1'] = [
            {
                'id': model.id,
                'name':model.name,
            }
            for model in Model.objects.all()
        ]

        data['shows1'] = [
            {
                'id': series.id,
                'code':series.code,
                'name': series.name,
            }
            for series in Series.objects.all()
        ]

        user = self.request.user

        data['can_export_schedule'] = user.has_perm('mps.view_schedule_report') or user.has_perm('mps.view_mps_page')
        return data

class SalesReportsView(PermissionRequiredMixin, TemplateView):
    template_name = 'mps/sales.html'
    permission_required = 'mps.view_mps_sales_report'

    def get_context_data(self, **kwargs):
        data = super(SalesReportsView, self).get_context_data(**kwargs)
        data['shows'] = [
            {
                'id': show.id,
                'name': show.name,
            }
            for show in Show.objects.all()
        ]

        user = self.request.user

        dealerships = get_user_mps_dealerships(user)

        data['dealerships'] = [
            {
                'id': dealership.id,
                'name': dealership.name,
            }
            for dealership in dealerships
        ]

        if user.has_perm('mps.view_sales_breakdown_all'):
            data['dealerships'].append({'id': SALESREPORT_DEALERSHIP_ID_ALL, 'name': 'All Dealerships'})

        data['can_export_sales_any'] = user.has_perm('mps.view_sales_breakdown_all')
        data['can_export_sales_user'] = user.has_perm('mps.view_sales_breakdown_own')
        data['can_export_sales_report'] = user.has_perm('mps.export_mps_sales_report')
        data['can_export_stock_report'] = user.has_perm('mps.export_mps_stock_report')
        data['can_view_mps_sales_report'] = user.has_perm('mps.view_mps_sales_report')

        data['can_export_runsheet'] = user.has_perm('mps.export_runsheet')
        data['can_extract_sales_report'] = user.has_perm('mps.extract_mps_sales_report')
        data['can_extract_stock_report'] = user.has_perm('mps.extract_mps_stock_report')
        data['can_export_month_sales_report'] = user.has_perm('mps.export_mps_month_sales_report')

        return data

class RunsheetView(ExportCSVMixin, PermissionRequiredMixin, View):
    permission_required = 'mps.export_runsheet'

    def get_headers(self, table=None):
        headers = [
            'Sequence. No',
            'Date',
            'First Name',
            'Last Name',
            'Suburb',
            'State',
            'Post Code',
            'E-mail Address',
            'Series Code',
            'Chassis #',
            'Order no',
            'Trade-in',
            'Deposit',
            'Retained Gross',
            'Sales Rep Name',
            'Desired Delivery Month',
            'Comments',
            'After Market',
            'Subject To',
        ]
        return headers

    def get_rows(self, table=None, id=None):

        orders = (Order.objects
            .filter(
            show_id=self.show_id,
            order_cancelled__isnull=True,
        )
            .order_by('id')
            .select_related(
            'customer__physical_address__suburb__post_code__state',
            'orderseries',
            'orderseries__series',
        )
        )

        orders = [order for order in orders if not order.is_quote()]

        rows = [
            [
                row + 1,
                get_sales_date(self, order),
                order.customer.first_name if order.customer else 'STOCK',
                order.customer.last_name if order.customer else '',
                getattr_nested(order, 'customer', 'physical_address', 'suburb', 'name', default=''),
                getattr_nested(order, 'customer', 'physical_address', 'suburb', 'post_code', 'state', 'code', default=''),
                getattr_nested(order, 'customer', 'physical_address', 'suburb', 'post_code', 'number', default=''),
                order.customer.email if order.customer else '',
                order.orderseries.series.code if hasattr(order, 'orderseries') else '',
                order.chassis,
                order.id,
                order.trade_in_comment,
                order.deposit_paid_amount,
                calculate_margin_without_gst(order),
                order.dealer_sales_rep.get_full_name(),
                order.delivery_date,
                order.price_comment,
                order.aftermarketnote.note if hasattr(order, 'aftermarketnote') and order.aftermarketnote else '',
                order.orderconditions.details if hasattr(order, 'orderconditions') and order.orderconditions else '',
            ]
            for row, order in enumerate(orders)
            ]
        return rows

    def get_file_name(self):
        return 'Runsheet for '

    def get_complete_file_name(self):
        return '{0}{1} - {2}'.format(self.get_file_name(), self.show.name,
                                     timezone.localtime(timezone.now()).strftime(settings.FORMAT_DATE_ONEWORD))

    def get(self, request, show_id=None):
        self.show_id = show_id
        self.show = get_object_or_404(Show, id=show_id)
        return self.write_csv()
  
        
class ScheduleCsvView(ExportCSVMixin, PermissionRequiredMixin, View):

    permission_required = 'mps.view_schedule_report'
 
    def calculate_count_ifs(self, data, date_val, dealer_ship_val, find_col):
        cnt = 0
        for dat in data:
            #print dat[0], date_val, 'date check', dealer_ship_val, dat[find_col]
            if dat[0] == date_val:
                #print dat[0], date_val, 'date check', dealer_ship_val, dat[find_col]
                if dat[find_col] == dealer_ship_val:
                    cnt += 1
        # if cnt >1:
        #   print 'match', dealer_ship_val, date_val, cnt
        # else:
        #   print 'omatch', dealer_ship_val, date_val
        return cnt

    def calculate_sum(self, xl_data, from_date, to_date):
        row_cell_old = {'A':1,'B':2, 'C':3, 
        'D':4,'E':5,'F':6,'G':7,'H':8,'I':9,
        'J':10,'K':11,'L':12,'M':13,'N':14,
        'O':15,'P':16,'Q':17,'R':18,'S':19,'T':20,
        'U':21,'V':22,'W':23,'X':24,'Y':25,'Z':26,
        'AA':27,'AB':28, 'AC':29, 'AD':30,'AE':31,'AF':32,'AG':33,
        'AH':34,'AI':35,'AJ':36,'AK':37,'AL':38,'AM':39,
        'AN':40,'AO':41,'AP':42,'AQ':43,'AR':44,'AS':45,'AT':46,'AU':47,
        'AV':48,'AW':49, 'AX':50,'AY':51,'AZ':52,
        'BA':53,'BB':54, 'BC':55, 'BD':56,'BE':57,'BF':58,'BG':59,
        'BH':60,'BI':61, 'BJ':62,'BK':63,'BL':64, 'BM':65,
        'BN':66,'BO':67,'BP':68,'BQ':69,'BR':70,'BS':71,'BT':72,'BU':73,
        'BV':74,'BW':75, 'BX':76,'BY':77,'BZ':78}
        total_col_max = 'BV'
        for k, v in list(row_cell_old.items()):
            if v == len(xl_data[0])-2:
                total_col_max = k
        #print total_col_max
        #print from_date, to_date
        if from_date == 1:
            row_cell = row_cell_old
        else:
            rowc = {} 
            for rt in range(from_date+1, 79):
                for k,v in list(row_cell_old.items()):
                    if v == rt:
                       rowc[k] = rt-from_date+1
            row_cell = rowc
        #print row_cell, total_col_max
        mod_data = []
        for row in xl_data:
            rdata = []
            for cell in row[0:-1]:
                if cell and isinstance(cell, str) :
                    if cell.find('=SUM(')!=-1:
                        calc = cell.replace('=SUM(', '').replace(')', '').split('+')
                        if len(calc) != 1 and calc[0].find(':')==-1:
                            sval = 0
                            for cf in calc:
                                cid = "".join([str(s) for s in cf if s.isdigit()])
                                tid = row_cell.get(cf.replace(cid, ''))
                                if xl_data[int(cid)-1][int(tid)-1].find('=SUM(')!=-1:
                                    sval += mod_data[int(cid)-1][int(tid)-1]
                                else:
                                    sval += xl_data[int(cid)-1][int(tid)-1]
                            rdata.append(sval)
                        else:
                            sval = 0
                            re, re1 = calc[0].split(':')
                            recid = "".join([str(s) for s in re if s.isdigit()])
                            retid = row_cell.get(re.replace(recid, ''))

                            re1cid = "".join([str(s) for s in re1 if s.isdigit()])
                            re1tid = row_cell.get(re1.replace(re1cid, ''))
                            
                            # if retid != re1tid:
                            #     print 'same error no match'
                            for uy in range(int(recid), int(re1cid)+1):
                                sval += xl_data[uy-1][retid-1]
                            rdata.append(sval)
                    else:
                        if cell[0] == '=' and cell.find('/')!=-1:
                            avg_col = cell.replace('=', '').split('/')
                            #print avg_col[0], avg_col[1], 'trerr'
                            avg1 = "".join([s for s in avg_col[0] if not s.isdigit()])
                            avg2 = "".join([s for s in avg_col[1] if not s.isdigit()])
                            for k,v in list(row_cell_old.items()):
                                if v == row_cell.get(avg1):
                                    av1 = k
                                if v == row_cell.get(avg2):
                                    av2 = k
                            fcellval = "="+av1+avg_col[0].replace(avg1, '')+'/'+av2+avg_col[1].replace(avg1, '')
                            #print fcellval, 'trerr2'
                            rdata.append(fcellval)
                        else:
                            rdata.append(cell)
                else:
                        rdata.append(cell)
            if row[-1]:
                if row[-1].find('=SUM(')!=-1:
                    if row[-1].find('+')!=-1:
                        rfval = []
                        for val in row[-1].replace('=SUM(', '').replace(')', '').split('+'):
                            if val[0:len(total_col_max)] == total_col_max:
                                rfval.append(val)
                                break
                            else:
                                rfval.append(val)
                        rfgval = '=SUM('+"+".join(rfval)+')'
                        #print rfgval
                        rdata.append(rfgval)
                    elif row[-1].find(':')!=-1:
                        rfval = []
                        avw1, avw2 = row[-1].replace('=SUM(', '').replace(')', '').split(':')
                        rfval.append(avw1)
                        avgw2 = "".join([s for s in avw2 if s.isdigit()])
                        rfval.append(total_col_max+avgw2)
                        rfgval = '=SUM('+":".join(rfval)+')'
                        #print rfgval, "total sum"
                        rdata.append(rfgval)
                elif row[-1][0] == '=' and row[-1].find('/')!=-1:
                    avg_col = row[-1].replace('=', '').split('/')
                    #print avg_col[0], avg_col[1], "ga"
                    avg1 = "".join([s for s in avg_col[0] if not s.isdigit()])
                    avg2 = "".join([s for s in avg_col[1] if not s.isdigit()])
                    for k,v in list(row_cell_old.items()):
                        if v == len(row):
                            av1 = k
                        if v == len(row):
                            av2 = k
                    #print av1, av2, 'ga2'
                    fcellval = "="+av1+avg_col[0].replace(avg1, '')+'/'+av2+avg_col[1].replace(avg1, '')
                    #print fcellval, 'ga3'
                    rdata.append(fcellval)
                    #print "-----"
                else:
                    #print row[-1], 'fijsdfsd'
                    rdata.append(row[-1])
            else:
                rdata.append(row[-1])
            mod_data.append(rdata)
        date_cols = []
        for dt in mod_data[0][1:-1]:
            if dt not in date_cols:
                date_cols.append(dt)
        total_cap_col = 266
        cera = 1
        for dra in date_cols:
            dra = datetime.strptime(dra, settings.FORMAT_DATE_MONTH).date()
            schedule_month = MonthPlanning.objects.get_or_create(production_month=dra , production_unit=1)[0]
            schedule_month_2 = MonthPlanning.objects.get_or_create(production_month=dra , production_unit=2)[0]
            capacity = schedule_month.get_capacity(1) + schedule_month.get_capacity(2)
            mod_data[total_cap_col][cera] = capacity
            cera+=2

        return mod_data

    
 
    def read_file(self, xldata, from_date, to_date):
        excel_data = []
        root_dir = os.path.dirname(os.path.abspath(__file__))
        fpath = os.path.join(root_dir, 'static/mps/MPS Master template.xlsx')
        master_sheet_name  = 'MPS Sheet'
        wbook = openpyxl.load_workbook(fpath)
        wsheet = wbook.get_sheet_by_name(master_sheet_name)
        from_date = from_date[0:-3]
        to_date = to_date[0:-2]
        if from_date is None or to_date is None:
            return "Invalid date range, from_date: '%s', to_date: '%s'"%(from_date, to_date)
        date_cell = {'2018-01':1,'2018-01-':2, '2018-02':3, 
        '2018-02-':4,'2018-03':5,'2018-03-':6,'2018-04':7,'2018-04-':8,'2018-05':9,
        '2018-05-':10,'2018-06':11,'2018-06-':12,'2018-07':13,'2018-07-':14,
        '2018-08':15,'2018-08-':16,'2018-09':17,'2018-09-':18,'2018-10':19,'2018-10-':20,
        '2018-11':21,'2018-11-':22,'2018-12':23,'2018-12-':24,'2019-01':25,'2019-01-':26,
        '2019-02':27,'2019-02-':28, '2019-03':29, '2019-03-':30,'2019-04':31,'2019-04-':32,
        '2019-05':33,'2019-05-':34,'2019-06':35,'2019-06-':36,'2019-07':37,
        '2019-07-':38,'2019-08':39,'2019-08-':40,'2019-09':41,'2019-09-':42,'2019-10':43,'2019-10-':44,
        '2019-11':45,'2019-11-':46, '2019-12':47,'2019-12-':48,'2020-01':49, '2020-01-':50,
        '2020-02':51,'2020-02-':52,'2020-03':53,'2020-03-':54, '2020-04':55, '2020-04-':56,
        '2020-05':57,'2020-05-':58,'2020-06':59,
        '2020-06-':60,'2020-07':61, '2020-07-':62,'2020-08':63,'2020-08-':64, '2020-09':65,
        '2020-09-':66,'2020-10':67,'2020-10-':68,'2020-11':69,'2020-11-':70,'2020-12':71,
        '2020-12-':72,'BU':73, 'BV':74,'BW':75, 'BX':76,'BY':77,'BZ':78}
        climit = [0]
        climit.extend(list(range(date_cell.get(from_date), date_cell.get(to_date)+1)))
        total_col = 73
        climit.append(total_col)

        for row in wsheet.iter_rows():
            row_data = []
            clen = 0
            for cell in row:
                if clen in climit:
                    if isinstance(cell.value, datetime):
                        date_str = cell.value.strftime(settings.FORMAT_DATE_MONTH)
                        row_data.append(date_str)
                    else:
                        #row_data.append(cell.value)
                        if cell.data_type == 'f':
                            rvalue = cell.value
                            if rvalue.find('Schedule Export Jan-Dec 19')!=-1:
                                if rvalue.find('COUNTIFS')!=-1:
                                    data_split = rvalue.replace('$', '').split(',')
                                    date_cmp = data_split[1]
                                    val_cmp = data_split[3].replace(')', '')
                                    #print date_cmp, val_cmp
                                    #print wsheet[date_cmp].value.strftime("%d-%m-%Y"), wsheet[val_cmp].value
                                    find_col = 7 #for 'h' col
                                    if rvalue.find("Schedule Export Jan-Dec 19'!$G:$G")!=-1:
                                        find_col = 6 #for'g' col
                                        val_result = self.calculate_count_ifs(xldata, wsheet[date_cmp].value.strftime(settings.FORMAT_DATE_MONTH), wsheet[val_cmp].value, find_col)
                                        #rvalue = cell.value.replace("Schedule Export Jan-Dec 19'!$A:$A", "A317:A700")
                                        #rvalue = rvalue.replace("Schedule Export Jan-Dec 19'!$G:$G", "G317:G700")
                                        #rvalue = rvalue.replace("Schedule Export Jan-Dec 19'!$H:$H", "H317:H700")
                                        #row_data.append(rvalue.replace('$', ''))
                                        #row_data.append(0)
                                        row_data.append(val_result)
                                    elif rvalue.find("Schedule Export Jan-Dec 19'!$H:$H")!=-1:
                                        val_result = self.calculate_count_ifs(xldata, wsheet[date_cmp].value.strftime(settings.FORMAT_DATE_MONTH), wsheet[val_cmp].value, find_col)
                                        row_data.append(val_result)
                                    else:
                                        row_data.append('dyjsddkdjfkdj')
                                else:
                                    row_data.append(cell.value.replace('$', ''))
                            else:
                                row_data.append(cell.value.replace('$', ''))
                        else:
                            row_data.append(cell.value)
                clen += 1

            # print('read_file 2')
            if row_data:
                excel_data.append(row_data)
        wbook.close()
        return self.calculate_sum(excel_data, date_cell.get(from_date), date_cell.get(to_date))

    def get_headers(self, table=None):
        return self.resp_data[0]

    def get_rows(self, table=None):
        return self.resp_data[1:]

    def get_file_name(self):
        return 'MPS Report '

    def get_complete_file_name(self):
        return '{0} {1} - {2}'.format(self.get_file_name(), self.date_from, self.date_to)

    def get_xl_data(self):
        rawdata = (Order \
                    .objects \
                    .filter(
                    build__build_order__production_month__gte=self.date_from,
                    build__build_order__production_month__lte=self.date_to,
                    ) \
                    .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                    .select_related(
                    'build__build_order',
                    'orderseries',
                    'orderseries__series',
                    'orderseries__series__model',
                    'dealership',
                )
        )

        rawdata = [order for order in rawdata] 

        rows = [
            [
                 
                order.build.build_order.production_month.strftime(settings.FORMAT_DATE_MONTH),
                str(order.build.build_order.order_number),
                order.build.build_date.strftime(settings.FORMAT_DATE) if order.build.build_date else '',
                get_status(order),
                str(order.id),
                order.chassis,
                order.get_series_code(),
                order.dealership.name,
            ]
            for order in rawdata
            ]

      
        return rows

    def get(self, request, * args, **kwargs):
        self.date_from = kwargs['date_from']
        self.date_to = kwargs['date_to']
        self.type = kwargs['type']

        if self.date_from > self.date_to:
            return HttpResponseBadRequest("The start date is greater than the end date.")
        
        data = self.get_xl_data()
        self.resp_data = self.read_file(data, self.date_from, self.date_to)
        return self.write_csv()
        

def getattr_nested(obj, *args, **kwargs):
    """
    Checks that obj.arg1 is defined and not None
    Then check obj.arg1.arg2 etc, until all args have been checked
    Returns True if all args are defined and not None

    >>> # A base object() has no __dict__ so we need to create a dummy class for testing
    >>> class EmptyObject(object):
    ...     pass
    >>> x = EmptyObject()
    >>> setattr(x, 'a', EmptyObject())
    >>> setattr(x.a, 'b', EmptyObject())
    >>> setattr(x.a.b, 'c', None)
    >>> setattr(x.a.b, 'd', 4)
    >>> setattr(x.a.b, 'e', {})
    >>> setattr(x.a.b, 'f', EmptyObject())
    >>> setattr(x.a.b, 'g', False)
    >>> check_object_chain(x, 'a')
    True
    >>> check_object_chain(x, 'aaa')
    False
    >>> check_object_chain(x, 'a', 'b')
    True
    >>> check_object_chain(x, 'a', 'bbb')
    False
    >>> check_object_chain(x, 'a', 'b', 'c')
    False
    >>> check_object_chain(x, 'a', 'b', 'ccc')
    False
    >>> check_object_chain(x, 'a', 'b', 'd')
    True
    >>> check_object_chain(x, 'a', 'b', 'e')
    True
    >>> check_object_chain(x, 'a', 'b', 'f')
    True
    >>> check_object_chain(x, 'a', 'b', 'g')
    True
    """
    default = kwargs.get('default')

    try:
        value = functools.reduce(getattr, args, obj)
        return value
    except AttributeError:
        return default



def calculate_margin_without_gst(order):

    price_affecting_order_skus = order.ordersku_set.filter(base_availability_type__in=(SeriesSKU.AVAILABILITY_OPTION, SeriesSKU.AVAILABILITY_UPGRADE))

    retail_total = (
        (order.orderseries.retail_price if hasattr(order, 'orderseries') and order.orderseries.retail_price else 0) +
        (order.price_adjustment_retail or 0) +
        (order.after_sales_retail or 0) +
        sum(osku.sku.retail_price or 0 for osku in price_affecting_order_skus) +
        sum(specialfeature.retail_price or 0 for specialfeature in order.specialfeature_set.all())
    )
    wholesale_total = (
        (order.orderseries.wholesale_price if hasattr(order, 'orderseries') and order.orderseries.wholesale_price else 0) +
        (order.price_adjustment_wholesale or 0) +
        (order.after_sales_wholesale or 0) +
        sum(osku.sku.wholesale_price or 0 for osku in price_affecting_order_skus) +
        sum(specialfeature.wholesale_price or 0 for specialfeature in order.specialfeature_set.all()) +
        order.dealer_load
    )

    wholesale_total += order.trade_in_write_back

    return round((retail_total - wholesale_total) / Decimal(1.1), 2)

def get_sales_date(export_csv_mixin, order):
    """
    Calls the datetime conversion method from ExportCSVMixin to turn order's relevant date into desired format
    """
    if order.is_order_converted:
        if order.order_converted:
            return export_csv_mixin.convert_date_time_to_local(order.order_converted)
        else:
            return ''
    elif order.order_submitted:
        return export_csv_mixin.convert_date_time_to_local(order.order_submitted)
    else:
        return ''

class SalesView(ExportCSVMixin, PermissionRequiredMixin, View):
    permission_required = 'mps.export_mps_sales_report'

    def get_retail_sales(self,temp_id):

        date_from = datetime.strptime(self.date_from, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.strptime(self.date_to, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.combine(date_to, datetime.max.time())  # get all orders of that same day
       
        if date_from is not None :
            
            orders = (Order.objects
                .filter(
                    order_submitted__gte=date_from,
                    order_submitted__lte=date_to,
                    order_cancelled__isnull=True,
                    dealership_id= self.tempid,
                    is_order_converted=0,
                    customer_id__isnull = False,
                )
                .select_related(
                'dealership',
                'orderseries',
                ).select_related('series')
                .select_related('model')
                .select_related('orderseries__series__code')
                .values('orderseries__series__model__name','orderseries__series__code')
                .annotate(mycount = Count('order_submitted',distinct=True)).order_by('orderseries__series__code') 
            )

            orders1 = orders.order_by('orderseries__series__code')

            model_count = orders1.values('orderseries__series__model__name').annotate(the_count=Count('orderseries__series__model__name')).order_by('orderseries__series__model__name')
            models_leftout = Model.objects.values('name').exclude(name__in = [item['orderseries__series__model__name'] for item in model_count]).values_list('name') 

            model_count = [item for item in model_count]
            all_models=[]
            for key in model_count:
                model_list=[]
                model_list.append(key['orderseries__series__model__name'])
                model_list.append(key['the_count'])
                all_models.append(model_list)
                 
            models_leftout=[item for item in models_leftout]
            #add 0
            for i in models_leftout:
                k=list(i)
                k.append(0)
                all_models.append(k)

            series_list=[]
            for key  in orders1:
                alllist=[]
                alllist.append(key['orderseries__series__model__name'] )
                alllist.append(key['orderseries__series__code'])
                alllist.append(key['mycount'])
                series_list.append(alllist)

            total_retail_sales = orders1.aggregate(Sum('mycount',default=0))
            
            total_retail = total_retail_sales['mycount__sum'] or 0
        

            #gets series  which do not exist using left join null in the above queryset -- excluded series
            series_remaining = Series.objects.select_related('model').values('code').exclude(code__in = [item['orderseries__series__code'] for item in orders1]).values('orderseries__series__code').exclude(orderseries__series__code__isnull = True).values_list('model__name','code',).distinct()
            test1 = [item for item in series_remaining]  
        
            newlist=[]
            # #Set mycount to 0 for non present series 
            for i in range(0,len(series_remaining)):
                # addmycount=[]
                addmycount=list(series_remaining[i])
                addmycount.append(0)
                newlist.append(addmycount)
               
            #Union of series present and not present
            report = list(chain(series_list,newlist))
            report.sort()
            
            test1 = [item for item in report]  
            
            indexpos=[]
            for m  in  all_models:
                t1 = [i for i, lst in enumerate(test1) if m[0] in lst][0] 
                indexpos.append(t1)

            indexpos.sort(reverse=True)
            all_models.sort(reverse=True)
            
            [j.pop(0) for j in test1] 
            
            for i in range(0,len(indexpos)):
                test1.insert(indexpos[i],all_models[i])

            test1.insert(0,['Total Sales',total_retail])
            return test1


    def get_stock_sales(self,temp_id):

        date_from = datetime.strptime(self.date_from, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.strptime(self.date_to, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.combine(date_to, datetime.max.time())  # get all orders of that same day
       
        if date_from is not None :
            
            orders = (Order.objects
                .filter(
                    order_converted__gte=date_from,
                    order_converted__lte=date_to,
                    order_cancelled__isnull=True,
                    dealership_id= self.tempid,
                    is_order_converted=1,
                    order_converted__isnull=False,
                    customer_id__isnull = False,
                )
                .select_related(
                'dealership',
                'orderseries',
                ).select_related('series')
                .select_related('model')
                .select_related('orderseries__series__code')
                .values('orderseries__series__model__name','orderseries__series__code')
                .annotate(mycount = Count('order_submitted',distinct=True)).order_by('orderseries__series__code')                
            )

            orders1 = orders.order_by('orderseries__series__code')

            model_count = orders1.values('orderseries__series__model__name').annotate(the_count=Count('orderseries__series__model__name')).order_by('orderseries__series__model__name')
            models_leftout = Model.objects.values('name').exclude(name__in = [item['orderseries__series__model__name'] for item in model_count]).values_list('name') 

            model_count = [item for item in model_count]
            all_models=[]
            for key in model_count:
                model_list=[]
                model_list.append(key['orderseries__series__model__name'])
                model_list.append(key['the_count'])
                all_models.append(model_list)
                 
            models_leftout=[item for item in models_leftout]
            #add 0
            for i in models_leftout:
                k=list(i)
                k.append(0)
                all_models.append(k)

            series_list=[]
            for key  in orders1:
                alllist=[]
                alllist.append(key['orderseries__series__model__name'] )
                alllist.append(key['orderseries__series__code'])
                alllist.append(key['mycount'])
                series_list.append(alllist)

            total_stock_sales = orders1.aggregate(Sum('mycount',default=0))
            
            total_stock = total_stock_sales['mycount__sum'] or 0

             
            #gets series using left join null exclude which do not exist in the above queryset -- excluded series
            series_remaining = Series.objects.select_related('model').values('code').exclude(code__in = [item['orderseries__series__code'] for item in orders1]).values('orderseries__series__code').exclude(orderseries__series__code__isnull = True).values_list('model__name','code',).distinct()
            test1 = [item for item in series_remaining]  
        
            newlist=[]
            # #Set mycount to 0 for non present series 
            for i in range(0,len(series_remaining)):
                # addmycount=[]
                addmycount=list(series_remaining[i])
                addmycount.append(0)
                newlist.append(addmycount)
               
            #Union of series present and not present
            report = list(chain(series_list,newlist))
            report.sort()
            
            test1 = [item for item in report]  
            
            indexpos=[]
            for m  in  all_models:
                t1 = [i for i, lst in enumerate(test1) if m[0] in lst][0] 
                indexpos.append(t1)

            indexpos.sort(reverse=True)
            all_models.sort(reverse=True)
            
            [j.pop(0) for j in test1] 
            
            for i in range(0,len(indexpos)):
                test1.insert(indexpos[i],all_models[i])

            test1.insert(0,['Total Sales',total_stock])
            return test1


    def print_output(self,dealership_id):
        
        self.tempid = self.dealership_id

        retail_sale = self.get_retail_sales(dealership_id)
        
        stock_sale = self.get_stock_sales(dealership_id)
        
        [j.pop(0) for j in stock_sale]
        
        series_sum1 = list(zip(*retail_sale))[1]
        series_sum2 = list(zip(*stock_sale))[0]
        
        res = [sum(pair) for pair in zip(series_sum1, series_sum2)]

        output=[a + b for a, b in zip(retail_sale, stock_sale)] 

        sumresult = list([[el] for el in res]) 

        output = [ a + b for a, b in zip(output,sumresult )] 

        output.insert(0,['Model','Retail Sales','Stock Sales','Total'])

        dname = Dealership.objects.get( id = self.dealership_id) 
        
        output.insert(0,['Dealer ','',str(dname)])
        
        return output 

    
    def print_for_all_dealership(self, tempid):

        master_list = [[],[]]

        dealer_data =  Dealership.objects.values('id').order_by('id')

        dealer_data = [item['id'] for item in dealer_data]
        
        i = 1 
       
        for x in dealer_data:

            self.tempid = int(x)
            
            retail_sale = self.get_retail_sales(self.tempid)
            stock_sale = self.get_stock_sales(self.tempid)


            first_list = [j.pop(0) for j in retail_sale]
            first_list.insert(0,'Model')
            first_list.insert(0,'Dealer')
            
            [j.pop(0) for j in stock_sale]

            series_sum1 = list(zip(*retail_sale))[0]
            series_sum2 = list(zip(*stock_sale))[0]
            
            
            res = [sum(pair) for pair in zip(series_sum1, series_sum2)]
            
            sumresult = list([[el] for el in res]) 

            output=[a + b for a, b in zip(retail_sale, stock_sale)] 
            
            output = [ a + b for a, b in zip(output,sumresult )] 

            output.insert(0,['Retail Sales','Stock Sales','Total'])

            dname = Dealership.objects.get( id = x) 
            
            output.insert(0,[' ','',str(dname)])
            
            if i == 1:
                master_list = list([[el] for el in first_list]) 
                master_list =  [a + b for a, b in zip(master_list,output )]
            else:
                master_list =   [a + b for a, b in zip(master_list,output )]
            i = i + 1
      
        return master_list
                
    def get_rows(self, table=None, id=None):
        rows = self.report_data [1:]
        return rows


    def get_headers(self, table=None):
        headers = self.report_data[0]
        return headers

    def get_file_name(self):
        return 'Retail - Stock Sales between '

    def get_complete_file_name(self):
        return '{0} {1} - {2}'.format(self.get_file_name(), self.date_from, self.date_to)
    

    def get(self, request, * args, **kwargs):
        
        self.dealership_id = None
        self.tempid = None
        self.date_from = kwargs['date_from']
        self.date_to = kwargs['date_to']
        self.dealership_id = kwargs['dealership_id']

        if get_user_mps_dealerships(request.user, self.dealership_id):
            self.dealership_id = int(self.dealership_id)
        
        # self.report_data = self.get_monthly_sales(self.dealership_id)

        if self.dealership_id != SALESREPORT_DEALERSHIP_ID_ALL:
            self.report_data = self.print_output(self.dealership_id)
        else:
            self.report_data = self.print_for_all_dealership(self.tempid)
    
        # return HttpResponse(json.dumps(self.report_data), content_type="application/json") 
        return self.write_csv()



class StockView(ExportCSVMixin, PermissionRequiredMixin, View):
    #template_name = 'mps/sales.html'
    permission_required = 'mps.export_mps_stock_report'

    def get_current_stock(self,dealerid):
       
        # if date_from is not None :
        # where order.order_submitted is not null and order.customer_id is null and order.salesforce_handover_recorded_at is not null 
        # and order.dealership_id = 3
        orders = (Order.objects
            .filter(
                order_submitted__isnull = False,
                customer_id__isnull = True,
                dispatch_date_actual__isnull = False,
                order_cancelled__isnull=True,
                dealership_id = dealerid,
            )
            .select_related(
            'dealership',
            'orderseries',
            'orderseries__series__code',
            'model',
            'series',
            )
            .values('orderseries__series__model__name','orderseries__series__code')
            .annotate(mycount = Count('id',distinct=True)).order_by('orderseries__series__code')
                            
        )
        orders1 = orders.order_by('orderseries__series__code')

        model_count = orders1.values('orderseries__series__model__name').annotate(the_count=Count('orderseries__series__model__name')).order_by('orderseries__series__model__name')
        models_leftout = Model.objects.values('name').exclude(name__in = [item['orderseries__series__model__name'] for item in model_count]).values_list('name') 

        model_count = [item for item in model_count]
        all_models=[]
        for key in model_count:
            model_list=[]
            model_list.append(key['orderseries__series__model__name'])
            model_list.append(key['the_count'])
            all_models.append(model_list)
                
        models_leftout=[item for item in models_leftout]
        #add 0
        for i in models_leftout:
            k=list(i)
            k.append(0)
            all_models.append(k)

        series_list=[]
        for key  in orders1:
            alllist=[]
            alllist.append(key['orderseries__series__model__name'] )
            alllist.append(key['orderseries__series__code'])
            alllist.append(key['mycount'])
            series_list.append(alllist)

        total_retail_sales = orders1.aggregate(Sum('mycount',default=0))
        
        total_retail = total_retail_sales['mycount__sum'] or 0
    
        #gets series  which do not exist using left join null in the above queryset -- excluded series
        series_remaining = Series.objects.select_related('model').values('code').exclude(code__in = [item['orderseries__series__code'] for item in orders1]).values('orderseries__series__code').exclude(orderseries__series__code__isnull = True).values_list('model__name','code',).distinct()
        test1 = [item for item in series_remaining]  
    
        newlist=[]
        # #Set mycount to 0 for non present series 
        for i in range(0,len(series_remaining)):
            # addmycount=[]
            addmycount=list(series_remaining[i])
            addmycount.append(0)
            newlist.append(addmycount)
            
        #Union of series present and not present
        report = list(chain(series_list,newlist))
        report.sort()
        
        test1 = [item for item in report]  
        
        indexpos=[]
        for m  in  all_models:
            t1 = [i for i, lst in enumerate(test1) if m[0] in lst][0] 
            indexpos.append(t1)

        indexpos.sort(reverse=True)
        all_models.sort(reverse=True)
        
        [j.pop(0) for j in test1] 
        
        for i in range(0,len(indexpos)):
            test1.insert(indexpos[i],all_models[i])

        # test1.append(['Total Stock',total_retail])
        test1.insert(0,['Total Stock',total_retail])
        return test1
     
    def get_future_stock(self,dealerid):

        orders = (Order.objects
            .filter(
                created_on__isnull = False,
                order_submitted__isnull = False,                
                customer_id__isnull = True,
                dispatch_date_actual__isnull = True,
                order_cancelled__isnull=True,
                dealership_id   =  dealerid,
                orderseries__series__model__name__isnull=False,
                orderseries__series__code__isnull=False,
            )
            .select_related(
            'dealership',
            'orderseries',
            'series',
            'model',
            'orderseries__series__code',
            )
            .values('orderseries__series__model__name','orderseries__series__code')
            .annotate(mycount = Count('id')).order_by('orderseries__series__code')
            
            # .exclude(orderseries__series__code__isnull = True)     
        )
        orders1 = orders.order_by('orderseries__series__code')
        # orders1 = [i for i in orders1 if not (i['orderseries__series__code'] is None  )] 
        orders1.filter(orderseries__series__code__isnull=True,
        orderseries__series__model__name__isnull=True,
        )

        model_count = orders1.values('orderseries__series__model__name').annotate(the_count=Count('id')).order_by('orderseries__series__model__name')

        models_leftout = Model.objects.values('name').exclude(name__in = [item['orderseries__series__model__name'] for item in model_count]).values_list('name') 

        model_count = [item for item in model_count]
        all_models=[]
        for key in model_count:
            model_list=[]
            model_list.append(key['orderseries__series__model__name'])
            model_list.append(key['the_count'])
            all_models.append(model_list)
                
        models_leftout=[item for item in models_leftout]
        #add 0
        for i in models_leftout:
            k=list(i)
            k.append(0)
            all_models.append(k)

        series_list=[]
        for key  in orders1:
            alllist=[]
            alllist.append(key['orderseries__series__model__name'] )
            alllist.append(key['orderseries__series__code'])
            alllist.append(key['mycount'])
            series_list.append(alllist)

        total_stock_sales = orders1.aggregate(Sum('mycount',default=0))

        total_stock = total_stock_sales['mycount__sum'] or 0

        #gets series using left join null exclude which do not exist in the above queryset -- excluded series
        series_remaining = Series.objects.select_related('model').values('code').exclude(code__in = [item['orderseries__series__code'] for item in orders1]).values('orderseries__series__code').exclude(orderseries__series__code__isnull = True).values_list('model__name','code',).distinct()
        test1 = [item for item in series_remaining]  
    
        newlist=[]
        # #Set mycount to 0 for non present series 
        for i in range(0,len(series_remaining)):
            # addmycount=[]
            addmycount=list(series_remaining[i])
            addmycount.append(0)
            newlist.append(addmycount)
            
        #Union of series present and not present
        report = list(chain(series_list,newlist))
        report.sort()
        
        test1 = [item for item in report]  
        
        indexpos=[]
        for m  in  all_models:
            t1 = [i for i, lst in enumerate(test1) if m[0] in lst][0] 
            indexpos.append(t1)

        indexpos.sort(reverse=True)
        all_models.sort(reverse=True)
        
        [j.pop(0) for j in test1] 
        
        for i in range(0,len(indexpos)):
            test1.insert(indexpos[i],all_models[i])

        # test1.append(['Future Stock',total_stock])
        test1.insert(0,['Future Stock',total_stock])
        return test1


    def print_output(self,dealership_id):
        
        self.dealerid = self.dealership_id

        retail_sale = self.get_current_stock(dealership_id)
        
        stock_sale = self.get_future_stock(dealership_id)
        
        [j.pop(0) for j in stock_sale]
        
        series_sum1 = list(zip(*retail_sale))[1]
        series_sum2 = list(zip(*stock_sale))[0]
        
        res = [sum(pair) for pair in zip(series_sum1, series_sum2)]

        output=[a + b for a, b in zip(retail_sale, stock_sale)] 

        sumresult = list([[el] for el in res]) 

        output = [ a + b for a, b in zip(output,sumresult )] 

        output.insert(0,['Model','Current Stock','Future Stock','Total'])

        dname = Dealership.objects.get( id = self.dealership_id) 
        
        output.insert(0,['Dealer ','',str(dname)])
        
        return output 

    
    def print_for_all_dealership(self, dealerid):

        master_list = [[],[]]

        dealer_data =  Dealership.objects.values('id').order_by('id')

        dealer_data = [item['id'] for item in dealer_data]
        
        i = 1 
       
        for x in dealer_data:

            self.dealerid = int(x)
            
            retail_sale = self.get_current_stock(self.dealerid)
            stock_sale = self.get_future_stock(self.dealerid)


            first_list = [j.pop(0) for j in retail_sale]
            first_list.insert(0,'Model')
            first_list.insert(0,'Dealer')
            
            [j.pop(0) for j in stock_sale]

            series_sum1 = list(zip(*retail_sale))[0]
            series_sum2 = list(zip(*stock_sale))[0]
            
            
            res = [sum(pair) for pair in zip(series_sum1, series_sum2)]
            
            sumresult = list([[el] for el in res]) 

            output=[a + b for a, b in zip(retail_sale, stock_sale)] 
            
            output = [ a + b for a, b in zip(output,sumresult )] 

            output.insert(0,['Current Stock','Future Stock','Total'])

            dname = Dealership.objects.get( id = x) 
            
            output.insert(0,[' ','',str(dname)])
            
            if i == 1:
                master_list = list([[el] for el in first_list]) 
                master_list =  [a + b for a, b in zip(master_list,output )]
            else:
                master_list =   [a + b for a, b in zip(master_list,output )]
            i = i + 1
      
        return master_list
     

   
    def get_rows(self, table=None, id=None):
        rows = self.report_data [1:]
        return rows


    def get_headers(self, table=None):
        headers = self.report_data[0]
        return headers

    def get_file_name(self):
        return 'Current and Future Stock Report '

    def get_complete_file_name(self):
        return '{0} {1} - {2}'.format(self.get_file_name(), self.dealership_id, self.dealership_id)
    

    def get(self, request, * args, **kwargs):
        
        self.dealership_id = None
        self.dealerid = None
        # self.date_from = kwargs['date_from']
        # self.date_to = kwargs['date_to']
        self.dealership_id = kwargs['dealership_id']

        if get_user_mps_dealerships(request.user, self.dealership_id):
            self.dealership_id = int(self.dealership_id)
        
        # self.report_data = self.get_future_stock(self.dealership_id)
        if self.dealership_id != SALESREPORT_DEALERSHIP_ID_ALL:
            self.report_data = self.print_output(self.dealership_id)
        else:
            self.report_data = self.print_for_all_dealership(self.dealerid)
        
        return self.write_csv()
   

class DataExtractView(ExportCSVMixin, PermissionRequiredMixin, View):

    permission_required = 'mps.extract_mps_sales_report'

    def get_rows(self, table=None, id=None):

        date_from = datetime.strptime(self.date_from, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.strptime(self.date_to, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.combine(date_to, datetime.max.time())

        if self.type == 'extract_retail_sales':
            
            orders = (Order.objects
                .filter(
                    order_submitted__gte=date_from,
                    order_submitted__lte=date_to,
                    order_cancelled__isnull=True,
                    #dealership_id= self.tempid,
                    is_order_converted=0,
                    customer_id__isnull = False,
                )
                
                .order_by('id')
                .select_related (
                    'customer__physical_address__suburb__post_code__state',
                    'orderseries',
                    'orderseries__series',
                    'dealership'
                )
            )

        else:

            orders = (Order.objects
                          
                .filter(
                    order_converted__gte=date_from,
                    order_converted__lte=date_to,
                    order_cancelled__isnull=True,
                    #dealership_id= self.tempid,
                    is_order_converted=1,
                    order_converted__isnull=False,
                    customer_id__isnull = False,
                )

                .order_by('id')
                .select_related (
                    'customer__physical_address__suburb__post_code__state',
                    'orderseries',
                    'orderseries__series',
                    'dealership',
                )                                    
            )
      
        if self.dealership_id != SALESREPORT_DEALERSHIP_ID_ALL:
                      
            orders = orders.filter(dealership_id=self.dealership_id)

        orders = [order for order in orders if not order.is_quote()]
        
        rows = [
            [
                order.dealership,
                get_sales_date(self, order),
                order.customer.first_name,
                order.customer.last_name,
                getattr_nested(order, 'customer', 'physical_address', 'suburb', 'name', default=''),
                getattr_nested(order, 'customer', 'physical_address', 'suburb', 'post_code', 'state', 'code', default=''),
                getattr_nested(order, 'customer', 'physical_address', 'suburb', 'post_code', 'number', default=''),
                order.customer.email if order.customer else '',
                order.orderseries.series.code if hasattr(order, 'orderseries') else '',
                order.id,
                order.chassis,
                order.build.build_order.production_month.strftime(settings.FORMAT_DATE_MONTH),
                order.dealer_sales_rep.get_full_name(),
            ]
            for order in orders
            ]
        return rows

    def get_headers(self, table=None):

        headers = [
            'Dealership',
            'Order Placed Date',
            'First Name',
            'Last Name',
            'Suburb',
            'State',
            'Post Code',
            'E-mail Address',
            'Series Code',
            'Order #',
            'Chassis #',
            'Schedule Month',
            'Sales Rep Name',
        ]
        # if self.type == 'extract_retail_sales':
        #   # headers.insert(1, 'Order Placed Date')
        # else:
        #   # headers.insert(1, 'Order Converted Date')
        return headers

    def get_file_name(self):
        if self.type == 'extract_retail_sales':
            return 'Retail Sales extract between'
        else:
            return 'Stock Sales extract between'

    def get_complete_file_name(self):

        return '{0} {1} - {2}'.format(self.get_file_name(), self.date_from, self.date_to)

    def get(self, request, * args, **kwargs):

        self.dealership_id = None
        self.type = kwargs['type']
        self.date_from = kwargs['date_from']
        self.date_to = kwargs['date_to']
        self.dealership_id = kwargs['dealership_id']

        if get_user_mps_dealerships(request.user, self.dealership_id):
            self.dealership_id = int(self.dealership_id)
       
        return self.write_csv()


class StockDataExtractView(ExportCSVMixin, PermissionRequiredMixin, View):

    permission_required = 'mps.extract_mps_stock_report'

    def get_rows(self, table=None, id=None):        

        if self.type == 'extract_current_stock':
            
            orders = (Order.objects
                .filter(
                    order_submitted__isnull = False,
                    customer_id__isnull = True,
                    dispatch_date_actual__isnull = False,
                    order_cancelled__isnull=True,
                    #dealership_id = dealership_id,
                )
                
                .order_by('id')
                .select_related (
                    'customer__physical_address__suburb__post_code__state',
                    'orderseries',
                    'orderseries__series',
                    'dealership'
                )
            )

        else:

            orders = (Order.objects
                          
                .filter(
                    created_on__isnull = False,
                    order_submitted__isnull = False,
                    dispatch_date_actual__isnull = True,
                    order_cancelled__isnull=True,
                    #dealership_id   =  dealership_id,
                    #orderseries__series__model__name__isnull=False,
                    #orderseries__series__code__isnull=False,
                    customer_id__isnull = True,                    
                )

                .order_by('id')
                .select_related (
                    'customer__physical_address__suburb__post_code__state',
                    'orderseries',
                    'orderseries__series',
                    'dealership',
                )                                    
            )
      
        if self.dealership_id != SALESREPORT_DEALERSHIP_ID_ALL:
                      
            orders = orders.filter(dealership_id=self.dealership_id)

        orders = [order for order in orders if not order.is_quote()]
        
        rows = [
            [
                order.build.build_order.production_month.strftime(settings.FORMAT_DATE_MONTH),
                order.dealership,
                get_sales_date(self, order),
                order.build.build_date if order.build else '',
                # order.customer.first_name if order.customer else 'STOCK',
                order.orderseries.series.code if hasattr(order, 'orderseries') else '',
                order.id,
                order.chassis,
                order.dispatch_date_actual,
            ]
            for order in orders
            ]
        return rows

    def get_headers(self, table=None):

        headers = [
            'Scheduled Month',
            'Dealership',
            'Order Placed Date',
            'Production Date',
            # 'First Name',
            'Series Code',
            'Order #',
            'Chassis #',
            'Actual Dispatch Date'
        ]
        return headers

    def get_file_name(self):
        if self.type == 'extract_current_stock':
            return 'Current Stock Extract '
        else:
            return 'Future Stock Etract '

    def get_complete_file_name(self):

        return '{0} {1} - {2}'.format(self.get_file_name(), self.dealership_id, self.dealership_id)

    def get(self, request, * args, **kwargs):

        self.dealership_id = None
        self.type = kwargs['type']
        self.dealership_id = kwargs['dealership_id']

        if get_user_mps_dealerships(request.user, self.dealership_id):
            self.dealership_id = int(self.dealership_id)
       
        return self.write_csv()


if __name__ == "__main__":
    import doctest
    doctest.testmod()


#################################NEW FUN##############################

class MonthSalesView(ExportCSVMixin, PermissionRequiredMixin, View):
    permission_required = 'mps.export_mps_month_sales_report'

    def get_monthly_retail_sales(self,dealership_id): 
        
        date_from = datetime.strptime(self.date_from, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.strptime(self.date_to, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.combine(date_to, datetime.max.time())  # get all orders of that same day
      
        if self.dealership_id != SALESREPORT_DEALERSHIP_ID_ALL:
            
            orders = Series.objects.all()

            with_series = Series \
                .objects \
                .filter(
                orderseries__order__order_submitted__gte=date_from,
                orderseries__order__order_submitted__lte=date_to,
                orderseries__order__order_cancelled__isnull=True,
                orderseries__order__dealership_id= self.dealership_id,
                orderseries__order__is_order_converted=0,
                orderseries__order__customer_id__isnull = False,
                ) \
                .order_by('code', 'name') \
                .select_related(
                'orderseries',
                'order',
                'model',
                'dealership',
                'customer',
                'orderseries__series__code',
                'series__orderseries__order__order_submitted',
                'orderseries__order__customer__id',
            ) \
            .extra({'month': "Extract(month from order_submitted)" or '0'}) \
            .extra({'year': "Extract(year from order_submitted)" or '0'}) \
            .values_list('orderseries__series__model__name','orderseries__series__code','month','year') \
            .annotate(count_items=Count('id'))
            
            without_series =  orders.filter(~Q(orderseries__series_id__isnull = True)).extra(select= {'month':0,'year':0,'count_items':0 }).select_related('orderseries').select_related('order').select_related('model').select_related('series').values_list('model__name','code','month','year','count_items').order_by('code','name')

            test1 = [item for item  in with_series]
            test2 = [item for item  in without_series]
            all_series = test1 + test2
            all_series.sort()

            model_count = with_series.values_list('orderseries__series__model__name','month','year').annotate(the_count=Count('code')).order_by('orderseries__series__model__name','month','year')
            models_leftout =  without_series.filter(~Q(orderseries__series__model__name__isnull = True,)).distinct().extra(select= {'month':0,'year':0,'the_count':0 }).values_list('orderseries__series__model__name','month','year','year').order_by('orderseries__series__model__name','month','year')
            
            all_models1 =  list(chain (model_count.distinct() , models_leftout.distinct()))
            all_models = [list(item) for item in all_models1]
            
            model_list = list(set([item[0] for item in all_models]))
            model_list.sort()

            with_series = with_series.order_by('code')

            total_retail_sales = Series \
                .objects \
                .filter(
                orderseries__order__order_submitted__gte=date_from,
                orderseries__order__order_submitted__lte=date_to,
                orderseries__order__order_cancelled__isnull=True,
                orderseries__order__dealership_id= self.dealership_id,
                orderseries__order__is_order_converted=0,
                orderseries__order__customer_id__isnull = False,
                ) \
                .order_by('code', 'name') \
                .select_related(
                'orderseries',
                'order',
                'model',
                'dealership',
                'customer',
                'orderseries__series__code',
                'series__orderseries__order__order_submitted',
                'orderseries__order__customer__id',
            ) \
            .extra({'month': "Extract(month from order_submitted)" or '0'}) \
            .extra({'year': "Extract(year from order_submitted)" or '0'}) \
            .values_list('month','year') \
            .annotate(count_items=Count('id')) \
            .order_by('month','year')


            total_sales = [list(item) for item in total_retail_sales]

            for row,col in enumerate(total_sales):
                total_sales[row].insert(0,'Total_Retail_Sales')

            master_list=['Total_Retail_Sales']

            for item in model_list:
                master_list.append(item) 
                ser_list = [item1[1] for item1 in all_series if item in item1]
                ser_list.sort()
                ser_list = list(set(ser_list))
                master_list.extend(ser_list)
            
            all_series =  [list(item) for item in all_series]

            [j.pop(0) for j in all_series]

            report = all_series + all_models + total_sales

            sd = datetime.strptime(str(date_from), "%Y-%m-%d")
            ed = datetime.strptime(str(self.date_to), "%d-%m-%Y")
            month_list = [datetime.strptime('%2.2d-%2.2d' % (y, m), '%Y-%m').strftime('%b-%y')

            for y in range(sd.year, ed.year+1) \
            for m in range(sd.month if y==sd.year else 1, ed.month+1 if y == ed.year else 13)]
            
            report = [item for item in report if item[2] != 0 ]

            print_list=[]

            for item in master_list:
                list_elems = OrderedDict()
                list_elems['series_name'] = item
                for el in month_list:
                    list_elems[el] = 0 
                
                repla =[els for els in report if els[0] == list_elems['series_name'] ]

                for row in repla:

                    key_name = str(calendar.month_name[row[1]])[:3]
                    key_name = key_name +   "-" +  str(row[2])[-2:]
                    list_elems[str(key_name)] = row[3]
            
                print_list.append(list_elems)

            return print_list 

    def get_monthly_stock_sales(self,dealership_id):
    
        date_from = datetime.strptime(self.date_from, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.strptime(self.date_to, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.combine(date_to, datetime.max.time())  # get all orders of that same day
      
        if self.dealership_id != SALESREPORT_DEALERSHIP_ID_ALL:
            
            orders = Series.objects.all()
            with_series = (Series.objects.filter(Q(    
                # orderseries__series_id__isnull = True,
                orderseries__order__order_converted__gte=date_from,
                orderseries__order__order_converted__lte=date_to,
                orderseries__order__order_cancelled__isnull=True,
                orderseries__order__dealership_id= self.dealership_id,
                orderseries__order__is_order_converted=1,
                orderseries__order__customer_id__isnull = False,)
            )
            .extra ({'month': "Extract(month from order_converted)" or '0'})
            .extra ({'year':"Extract(year from order_converted)" or '0'})
            .select_related('orderseries')
            .select_related('order')
            .select_related('model')
            .select_related('dealership')
            .select_related('customer')
            .select_related('orderseries__series__code')
            .select_related('series__orderseries__order__order_submitted')
            .select_related('orderseries__order__customer__id')
            .values_list('orderseries__series__model__name','orderseries__series__code','month','year')
            .annotate(count_items=Count('orderseries__order__id'))
            .order_by('code','name')
            )

            without_series =  orders.filter(~Q(orderseries__series_id__isnull = True)).select_related('orderseries').select_related('order').select_related('model').extra(select= {'month':0,'year':0,'count_items':0 }).values_list('model__name','code','month','year','count_items').order_by('code','name')

            test1 = [item for item  in with_series]
            test2 = [item for item  in without_series]
            all_series = test1 + test2
            all_series.sort()

            model_count = with_series.values_list('orderseries__series__model__name','month','year').annotate(the_count=Count('code')).order_by('orderseries__series__model__name','month','year')
            models_leftout =  without_series.filter(~Q(orderseries__series__model__name__isnull = True,)).distinct().extra(select= {'month':0,'year':0,'the_count':0 }).values_list('orderseries__series__model__name','month','year','year').order_by('orderseries__series__model__name','month','year')
            all_models1 =  list(chain (model_count.distinct() , without_series.distinct()))
            all_models = [list(item) for item in all_models1]
            model_list = list(set([item[0] for item in all_models]))
            model_list.sort()
            
            with_series = with_series.order_by('code')
            # total_stock_sales = with_series.annotate(tsum=Sum('orderseries__order__id',default=0),tcount= Count('orderseries__order__id',default=0,distinct=True)).values_list('month','year','tcount').order_by('month','year')
            
            total_stock_sales = (Series.objects.filter(Q(    
                # orderseries__series_id__isnull = True,
                orderseries__order__order_converted__gte=date_from,
                orderseries__order__order_converted__lte=date_to,
                orderseries__order__order_cancelled__isnull=True,
                orderseries__order__dealership_id= self.dealership_id,
                orderseries__order__is_order_converted=1,
                orderseries__order__customer_id__isnull = False,)
            )
            .extra ({'month': "Extract(month from order_converted)" or '0'})
            .extra ({'year':"Extract(year from order_converted)" or '0'})
            .select_related('orderseries')
            .select_related('order')
            .select_related('model')
            .select_related('dealership')
            .select_related('customer')
            .select_related('orderseries__series__code')
            .select_related('series__orderseries__order__order_submitted')
            .select_related('orderseries__order__customer__id')
            .values_list('month','year')
            .annotate(count_items=Count('orderseries__order__id'))
            .order_by('month','year')
            )

            total_sales = [list(item) for item in total_stock_sales]

            for row,col in enumerate(total_sales):
                total_sales[row].insert(0,'Total_Stock_Sales')

            master_list=['Total_Stock_Sales']

            for item in model_list:
                master_list.append(item)    
                ser_list = [item1[1] for item1 in all_series if item in item1]
                ser_list=list(set(ser_list))
                ser_list.sort()
                master_list.extend(ser_list)

            all_series =  [list(item) for item in all_series]

            [j.pop(0) for j in all_series]

            report = all_series + all_models + total_sales
           
           # Prepare Month - Year Range  as dict Keys
            sd = datetime.strptime(str(date_from), "%Y-%m-%d")
            ed = datetime.strptime(str(self.date_to), "%d-%m-%Y")

            month_list = [datetime.strptime('%2.2d-%2.2d' % (y, m), '%Y-%m').strftime('%b-%y')

            for y in range(sd.year, ed.year+1) \
            for m in range(sd.month if y==sd.year else 1, ed.month+1 if y == ed.year else 13)]

            report = [item for item in report if item[2] != 0 ]

            print_list=[]
            
            for item in master_list:
                list_elems = OrderedDict()
                list_elems['series_name'] = item
                for el in month_list:
                    list_elems[el] = 0 
                
                repla =[els for els in report if els[0] == list_elems['series_name'] ]

                for row in repla:
                    key_name = str(calendar.month_name[row[1]])[:3]
                    key_name = key_name +   "-" +  str(row[2])[-2:]
                    list_elems[str(key_name)] = row[3]
            
                print_list.append(list_elems)

            
            return print_list  
    
            
    def get_all_monthly_sales(self,dealership_id):

        date_from = datetime.strptime(self.date_from, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.strptime(self.date_to, settings.FORMAT_DATE_DATEPICKER_DASH_FMT).date()
        date_to = datetime.combine(date_to, datetime.max.time())  # get all orders of that same day

        sd = datetime.strptime(str(date_from), "%Y-%m-%d")
        ed = datetime.strptime(str(self.date_to), "%d-%m-%Y")

        lst = [datetime.strptime('%2.2d-%2.2d' % (y, m), '%Y-%m').strftime('%b-%y')

        for y in range(sd.year, ed.year+1) \
        for m in range(sd.month if y==sd.year else 1, ed.month+1 if y == ed.year else 13)]

        month_list = ['Models']



        retail_monthly_sales = self.get_monthly_retail_sales(self.dealership_id)
            

        stock_monthly_sales = self.get_monthly_stock_sales(self.dealership_id)

        model_column = [ item['series_name'] for item in retail_monthly_sales]

        model_column = list([[el] for el in model_column]) 

        master_list = [[],[]]

        i = 1
        for period in lst:

            res1 = [ int(item[str(period)]) for item in retail_monthly_sales]
            
            res2 = [ int(item[str(period)]) for item in stock_monthly_sales]
            

            res1 = list([[el] for el in res1]) 
            res2 = list([[el] for el in res2]) 

            output = [a + b for a, b in zip(res1, res2)] 


            if i == 1:
                master_list = list([[el] for el in model_column]) 
                master_list =  [a + b for a, b in zip(model_column,output )]
            else:
                master_list =   [a + b for a, b in zip(master_list,output )]
            i = i + 1


            month_list.append(' ')
            month_list.append(period)

        
        header1 = [''] 
        for i in range(0,len(month_list)//2):
            header1.append('Retail Sale ')
            header1.append('Stock Sale ')

        master_list.insert(0,header1)
        
        master_list.insert(0,month_list)

        dname = Dealership.objects.get(id = self.dealership_id) 
            
        master_list.insert(0,[' ',' ',str(dname)])
        
        return master_list

    
    def get_rows(self, table=None, id=None):
        rows = self.report_data [1:]
        return rows


    def get_headers(self, table=None):
        headers = self.report_data[0]
        return headers

    def get_file_name(self):
        return 'Monthly Sales Report '

    def get_complete_file_name(self):
        return '{0} {1} - {2}'.format(self.get_file_name(), self.date_from, self.date_to)
    

    def get(self, request, * args, **kwargs):
        
        self.dealership_id = None
        self.tempid = None
        self.date_from = kwargs['date_from']
        self.date_to = kwargs['date_to']
        self.dealership_id = kwargs['dealership_id']

        if get_user_mps_dealerships(request.user, self.dealership_id):
            self.dealership_id = int(self.dealership_id)
        
        self.report_data = self.get_all_monthly_sales(self.dealership_id)
        

        # return HttpResponse(json.dumps(self.report_data), content_type="application/json") 
        return self.write_csv()
