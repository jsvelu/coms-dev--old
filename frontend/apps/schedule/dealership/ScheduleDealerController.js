import _ from 'lodash';

export default app => {

    require('./ScheduleDealerApiService')(app);

    app.controller('ScheduleDealerController', function (
        $anchorScroll,
        $rootScope,
        $scope,
        ScheduleDealerApiService
    ) {

        $scope.saveLoading = false;
        $scope.month_picker= new Date();
        $scope.actual_capacity=0;
        $scope.total_capacity=0;
        $scope.capacity_sum;       
        $scope.defaultDate = new Date(new Date() - 1000*3600*24*3);
        $scope.successMessages = [];
        $scope.errorMessages = [];

        const setAllData = (data,actual_capacity_parm=0) => {
            $scope.all_data = data;
            $scope.actual_capacity=actual_capacity_parm;
            calculate_totals();
            $anchorScroll('message-anchor');
        };

        const calculate_totals = ()=>{
            let allData=$scope.all_data;
            $scope.total_capacity=0
            allData.forEach(element => {
                $scope.total_capacity += element.capacity_allotted             
            });
        }

        ScheduleDealerApiService.getInitialData().then((data) => {

            setAllData(data.data,data.actual_capacity_allocated);
            $rootScope.permissions = data.permissions;
            
            
        });

        const dataprocess = ()=>{
            let allData=$scope.all_data;
            var dealer_capacity_data=[];
            allData.forEach(element => {
                dealer_capacity_data.push({
                    id: element.id,
                    dealer_id: element.dealer_id,
                    production_month:element.production_month,  
                    dealer_name:element.name,
                    capacity_value: document.getElementById(element.dealer_id.toString()).value
                });               
            });
            var dealer_capacity_data_json=JSON.stringify(dealer_capacity_data);
            return dealer_capacity_data_json;
        }

        $scope.capacity_sum = ()=>{
            let allData=$scope.all_data;
            $scope.total_capacity=0
            allData.forEach(element => {
                $scope.total_capacity += parseInt(document.getElementById(element.dealer_id).value)             
            });
        }

       
        $scope.save = () => {
                      
            $scope.saveLoading = true;
            ScheduleDealerApiService.saveData(dataprocess(),$scope.month_picker)
                .then(
                    (result) => {
                        $scope.successMessages = ['Data saved successfully'];
                        $scope.errorMessages = [];
                        // console.log(result.data)
                        setAllData(result.data,result.actual_capacity_allocated);
                    },
                    (err) => {
                        let message_list = err.data;
                        if (typeof(message_list) == typeof('')) {
                            message_list = [message_list];
                        }
                        $scope.errorMessages = message_list;
                    }
                )
                .finally(() => {
                    $scope.saveLoading = false;
                })

        };
        $scope.monthpicker_selection = () => {
            ScheduleDealerApiService.updateMonth($scope.month_picker)
            .then(
                (result) => {
                    $scope.successMessages = [];
                    $scope.errorMessages = [];
                    setAllData(result.data,result.actual_capacity_allocated);
                },
                (err) => {
                    let message_list = err.data;
                    if (typeof(message_list) == typeof('')) {
                        message_list = [message_list];
                    }
                    $scope.errorMessages = message_list;
                }
            )
            .finally(() => {
                $scope.saveLoading = false;
            })
        };
});
};
