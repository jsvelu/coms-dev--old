from django.conf.urls import url
from reports import views

app_name = 'reports'

urlpatterns = [
    url(r'^$', views.ReportsIndexView.as_view(), name='index'),
    url(r'^runsheet/(?P<show_id>\d*)', views.RunsheetView.as_view(), name='runsheet'),  # Using \d* to be able to do a reverse without parameter like {% url 'runsheet' %}. The View will return a 404 if parameter is missing.
    url(r'^series_pricelist/(?P<model_id>\d*)', views.ModelSeriesPriceListView.as_view(), name='series_pricelist'),
    url(r'^sku_pricelist/(?P<sku_category_id>\d*)/(?P<effective_date>\d*)', views.SKUPriceListView.as_view(), name='sku_pricelist'),
    url(r'^invoice_csv/(?P<type>\w*)/(?P<date_from>\d{2}-\d{2}-\d{4}\d*)/(?P<date_to>\d{2}-\d{2}-\d{4}\d*)/$', views.InvoiceView.as_view(), name='invoice_csv'),
    url(r'^sales/(?P<dealership_id>-?\d*)/(?P<date_from>\d{2}-\d{2}-\d{4}\d*)/(?P<date_to>\d{2}-\d{2}-\d{4}\d*)/$', views.SalesView.as_view()),
    url(r'^ready_view/(?P<date_from>\d{2}-\d{2}-\d{4}\d*)/(?P<date_to>\d{2}-\d{2}-\d{4}\d*)/$', views.ReadyForDispatchView.as_view(),name='ready_view'),
    url(r'^ready_export/(?P<date_from>\d{2}-\d{2}-\d{4}\d*)/(?P<date_to>\d{2}-\d{2}-\d{4}\d*)/$', views.ReadyForDispatchExportView.as_view(),name='ready_export'),
    url(r'^dispatch_view/(?P<date_from>\d{2}-\d{2}-\d{4}\d*)/(?P<date_to>\d{2}-\d{2}-\d{4}\d*)/$', views.DispatchMailView.as_view(),name='dispatch_view'),
    url(r'^dispatch_export/(?P<date_from>\d{2}-\d{2}-\d{4}\d*)/(?P<date_to>\d{2}-\d{2}-\d{4}\d*)/$', views.DispatchExportView.as_view(),name='dispatch_export'),
    url('vin_upload/', views.VinImport.as_view(), name="vin_upload"),
    url('vin_data_upload/', views.VinDataUpload.as_view(), name="vin_data_upload"),
    url('series_price_upload/', views.SeriesPriceImport.as_view(), name="series_price_upload"),
    url('series_price_update/', views.SeriesPriceUpload.as_view(), name="series_price_update"),
    url('sku_price_upload/', views.SkuPriceImport.as_view(), name="sku_price_upload"),
    url('sku_price_update/', views.SkuPriceUpload.as_view(), name="sku_price_update"),
    url(r'^view_series_price_audit/$', views.ViewSeriesPriceAudit.as_view(), name='view_series_price_audit'),
    url(r'^color', views.ColorSelectionSheetView.as_view(), name='color'),
]
