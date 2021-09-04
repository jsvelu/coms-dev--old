webpackJsonp([13],{0:function(a,t,e){a.exports=e(172)},121:function(a,t){"use strict";Object.defineProperty(t,"__esModule",{value:!0}),t.default=function(a){a.controller("LeadsController",["$scope","$timeout","ApiService","Upload",function(a,t,e,n){a.data={all_leads:[]},a.post=function(a){return e.post("leads/",a)},a.leads_table_config={url:"/api/leads/",data:{type:"all_leads"},dataSrc:"list",columns:[{data:"name",title:"Name"},{data:"post_code",title:"Post Code"},{data:"state",title:"State"},{data:"created",title:"Created"}]};var d=function(t){return function(){var e={type:t};return a.data.from_date&&(e.from=a.data.from_date.toISOString()),a.data.to_date&&(e.to=a.data.to_date.toISOString()),e}};a.leads_stats_config={url:"/api/leads-register/",data:d("lead_stats"),dataSrc:"data.dealerships",columns:[{title:"Name",data:"name"},{title:"Total",data:"total"},{title:"Won",data:function(a,t,e,n){return a.won+" ("+a["won_%"]+"%)"}},{title:"Lost",data:function(a,t,e,n){return a.lost+" ("+a["lost_%"]+"%)"}},{title:"Open",data:function(a,t,e,n){return a.open+" ("+a["open_%"]+"%)"}},{title:"Working",data:function(a,t,e,n){return a.working+" ("+a["working_%"]+"%)"}}]},a.advert_stats_config={url:"/api/leads-register/",data:d("lead_stats"),dataSrc:"data.sources",columns:[{title:"Name",data:"name"},{title:"Total",data:"total"},{title:"Won",data:function(a,t,e,n){return a.won+" ("+a["won_%"]+"%)"}},{title:"Lost",data:function(a,t,e,n){return a.lost+" ("+a["lost_%"]+"%)"}},{title:"Open",data:function(a,t,e,n){return a.open+" ("+a["open_%"]+"%)"}},{title:"Working",data:function(a,t,e,n){return a.working+" ("+a["working_%"]+"%)"}}]},a.charts={leadsByDealership:{type:"PieChart",displayed:!0,data:{cols:[{id:"dealership",label:"Dealership",type:"string",p:{}},{id:"leads",label:"Leads",type:"number",p:{}}],rows:[]},options:{title:"Leads by Dealership",fill:20,displayExactValues:!0,is3D:!0,chartArea:{width:"90%",height:"90%"}}},advertising:{type:"PieChart",displayed:!0,data:{cols:[{id:"source",label:"Source",type:"string",p:{}},{id:"leads",label:"Leads",type:"number",p:{}}],rows:[]},options:{title:"Leads by Source",fill:20,displayExactValues:!0,is3D:!0,chartArea:{width:"90%",height:"90%"}}}},a.onFilterDates=function(){a.data.leads_stats.ajax.reload(),a.data.advert_stats.ajax.reload()},a.onUpdateLeadsChart=function(t){a.charts.leadsByDealership.data.rows=[];for(var e=0;e<t.length;e++)a.charts.leadsByDealership.data.rows.push({c:[{v:t[e].name},{v:t[e].total}]})},a.onUpdateAdvertChart=function(t){a.charts.advertising.data.rows=[];for(var e=0;e<t.length;e++)a.charts.advertising.data.rows.push({c:[{v:t[e].name},{v:t[e].total}]})},a.onLeadsTableDraw=function(t){a.$apply(a.onUpdateLeadsChart(t.ajax.json().data.dealerships))},a.onAdvertTableDraw=function(t){a.$apply(a.onUpdateAdvertChart(t.ajax.json().data.sources))}}])},a.exports=t.default},172:function(a,t,e){"use strict";var n=e(10);e(121)(n),n.config(["$stateProvider",function(a){a.state("leads",{url:"",template:e(288),controller:"LeadsController"})}])},288:function(a,t){a.exports='<div class="container-fluid">\n    <div class="row" style="min-height:112px;"></div>\n\n    <div class="row">\n        <div class="col-sm-12">\n            <tabset>\n                <tab>\n                    <tab-heading>All Leads</tab-heading>\n                    <div class="row" style="min-height:40px;"></div>\n                    <ajax-data-table data-table="data.all_leads" data-config="leads_table_config"></ajax-data-table>\n                </tab>\n\n                <tab>\n                    <tab-heading>Statistics</tab-heading>\n\n                    <div class="row">\n                        <form>\n                            <div class="form-group col-sm-6">\n                                <label class="control-label">From</label>\n\n                                <div class="form-group">\n                                    <div class="input-group">\n                                        <input type="date" class="form-control" datepicker-popup\n                                               is-open="datepicker.from.opened"\n                                               ng-required="false" close-text="Close" ng-model="data.from_date"/>\n                                          <span class="input-group-btn">\n                                            <button type="button" class="btn btn-default" ng-click="datepicker.from.opened = true">\n                                                <i class="glyphicon glyphicon-calendar"></i></button>\n                                          </span>\n                                    </div>\n                                </div>\n                            </div>\n\n                            <div class="form-group col-sm-6">\n                                <label class="control-label">To</label>\n\n                                <div class="form-group">\n                                    <div class="input-group">\n                                        <input type="date" class="form-control" datepicker-popup\n                                               is-open="datepicker.to.opened"\n                                               ng-required="false" close-text="Close" ng-model="data.to_date"/>\n                                          <span class="input-group-btn">\n                                            <button type="button" class="btn btn-default" ng-click="datepicker.to.opened = true">\n                                                <i class="glyphicon glyphicon-calendar"></i></button>\n                                          </span>\n                                    </div>\n                                </div>\n                            </div>\n\n                            <button ng-click="onFilterDates()" class="btn btn-default">Filter</button>\n                        </form>\n                        </div>\n\n                        <div class="row">\n                            <h3>Leads</h3>\n                            <div class="col-md-6">\n                                <ajax-data-table data-table="data.leads_stats" data-config="leads_stats_config" data-on-draw="onLeadsTableDraw"></ajax-data-table>\n                            </div>\n                            <div class="col-md-6">\n                                <div google-chart chart="charts.leadsByDealership"></div>\n                            </div>\n                        </div>\n\n\n                        <div class="row">\n                            <h3>Advertising</h3>\n                            <div class="col-md-6">\n                                <ajax-data-table data-table="data.advert_stats" data-config="advert_stats_config" data-on-draw="onAdvertTableDraw"></ajax-data-table>\n                            </div>\n                            <div class="col-md-6">\n                                <div google-chart chart="charts.advertising"></div>\n                            </div>\n                        </div>\n                    </div>\n                </tab>\n            </tabset>\n        </div>\n    </div>\n</div>'}});