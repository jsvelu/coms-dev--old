import orders.urls
from django.urls import re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.conf.urls import include, url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns


from schedule.views import api
from schedule.views import api2
from schedule.views import export

app_name='schedule'


urlpatterns=[
url(r'^admin/', admin.site.urls),
# url(r'^orders/',include( orders.urls)),

]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
# urlpatterns += re_path(r'invoice_print/', api.job(), name='invoice_print'),
# urlpatterns += re_path(r'invoice_print/(?P<order_id>\d+)/$', api.InvoiceViewPrint.as_view(), name='invoice_print'),

urlpatterns_api = [
    re_path(r'^dashboard/dealer/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api.DealerScheduleDashboardAPIView.as_view()),
    re_path(r'^dashboard/initial/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api.ScheduleDashboardAPIView.as_view()), 
    re_path(r'^transport-dashboard/initial/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api.ScheduleTransportDashboardAPIView.as_view()),
    re_path(r'^dashboard/initialdata/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api.ScheduleTransportDashboardAPIView.as_view()),
    re_path(r'^dashboard/assign-production-dates', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/change-order-schedule-month', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/assign-production-dates', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/change-order-schedule-month', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/change-order-schedule-month-position', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/change-order-schedule-unit-position', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-order', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-transport-order', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-prodcomment-order', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-water-order', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-finalqccomment-order', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-dispatch-order', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-proddate', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-qcdate', api.DashboardTransportUpdateAPIView.as_view()),

    re_path(r'^dashboard/bulk-update-newlogic', api.DashboardUpdateAPIView.as_view()),
    
    re_path(r'^dashboard/update-waterdate', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-water-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-weigh-bridge', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-weigh-bridge-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-detailing', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-detailing-comments', api.DashboardTransportUpdateAPIView.as_view()),

    re_path(r'^dashboard/update-finalqcdate', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-chassis-section', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-chassis-section-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-building', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-building-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-aluminium', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-aluminium-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-prewire_section', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-prewire-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-plumbing_date', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-plumbing-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-finishing', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-finishing-comments', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-hold-caravans', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-dispatchdate', api.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard/update-lockdown', api.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard/production_status', api.ProductionStatusAPIView.as_view()),
    re_path(r'^dashboard/delay_status', api.DelayStatusAPIView.as_view()),
    
    
    re_path(r'^capacity/initial/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api.ScheduleCapacityAPIView.as_view()),
    re_path(r'^capacity/save$', api.ScheduleCapacityAPIView.as_view()),
    re_path(r'^planner/initial', api.SchedulePlannerAPIView.as_view()),
    re_path(r'^dealership/initial', api.DealerSchedulePlannerApiView.as_view()),
    re_path(r'^dealership/save', api.DealerSchedulePlannerApiView.as_view()),
    re_path(r'^dealership/update-month', api.DealerSchedulePlannerApiView.as_view()),
    re_path(r'^planner/save', api.SchedulePlannerAPIView.as_view()),
    re_path(r'^planner/update_month', api.SchedulePlannerAPIView.as_view()),
    re_path(r'^export/initial', api.ScheduleExportAPIView.as_view()),
    re_path(r'^export/initial', api.ScheduleExportAPIView.as_view()),
    
   # return ApiService.getData('schedule/dealerschedulecapacity/initial');
    ######### Schedule 2 #####################
    
    re_path(r'^dashboard2/initial/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api2.ScheduleDashboardAPIView.as_view()), 
    re_path(r'^transport-dashboard2/initial/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api2.ScheduleTransportDashboardAPIView.as_view()),
    re_path(r'^dashboard2/initialdata/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api2.ScheduleTransportDashboardAPIView.as_view()),
    re_path(r'^dashboard2/assign-production-dates', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/change-order-schedule-month', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/assign-production-dates', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/change-order-schedule-month', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/change-order-schedule-month-position', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/change-order-schedule-unit-position', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-order', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-transport-order', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-prodcomment-order', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-water-order', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-finalqc-order', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-dispatch-order', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-proddate', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-qcdate', api2.DashboardTransportUpdateAPIView.as_view()),
    
    re_path(r'^dashboard2/update-waterdate', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-water-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-weigh-bridge', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-weigh-bridge-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-detailing', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-detailing-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    
    re_path(r'^dashboard2/update-finalqcdate', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-chassis-section', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-chassis-section-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-building', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-building-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-aluminium', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-aluminium-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-prewire_section', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-prewire-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-finishing', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-finishing-comments', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-hold-caravans', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-dispatchdate', api2.DashboardTransportUpdateAPIView.as_view()),
    re_path(r'^dashboard2/update-lockdown', api2.DashboardUpdateAPIView.as_view()),
    re_path(r'^dashboard2/production_status', api2.ProductionStatusAPIView.as_view()), 


    re_path(r'^capacity2/initial/(?P<view_month>2\d{3}-[01]\d-[0-3]\d)$', api2.ScheduleCapacityAPIView.as_view()),
    re_path(r'^capacity2/save$', api2.ScheduleCapacityAPIView.as_view()),
    re_path(r'^planner2/initial', api2.SchedulePlannerAPIView.as_view()),
    re_path(r'^planner2/save', api2.SchedulePlannerAPIView.as_view()),
    re_path(r'^export2/initial', api2.ScheduleExportAPIView.as_view()),
    re_path(r'^export2/initial', api2.ScheduleExportAPIView.as_view()),
] 
urlpatterns_export = [
    re_path(r'^series-avg-csv', export.SeriesAvgCSVView.as_view(), name='export_series_csv'),
    re_path(r'^schedule-csv/(?P<unit_id>\d+)/(?P<date_from>2\d{3}-[01]\d)/(?P<date_to>2\d{3}-[01]\d)', export.ScheduleCSVView.as_view(), name='export_schedule_csv'),
    re_path(r'^specs-pdf/(?P<unit_id>\d+)/(?P<date_from>2\d{3}-[01]\d)', export.SchedulePDFView.as_view(), name='export_specs_pdf'),
    re_path(r'^productiondashboard-csv/(?P<unit_id>\d+)/(?P<category>\w*)/(?P<date_from>2\d{3}-[01]\d)/(?P<date_to>2\d{3}-[01]\d)', export.ProductionDashboardCSVView.as_view(), name='export_production_dashboard_csv'),
    re_path(r'^delaydashboard-csv/(?P<category>\w*)', export.DelayDashboardCSVView.as_view(), name='delaydashboard-csv'),
    re_path(r'^contractor/(?P<unit_id>\d+)/(?P<export_id>\d+)/(?P<date_from>2\d{3}-[01]\d)/(?P<date_to>2\d{3}-[01]\d)', export.ContractorExportView.as_view(), name='export_contractor_csv'),
]

