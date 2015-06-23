app = angular.module('ScorePoster', [])

app.controller('FormControl', ['$scope', '$http', function($scope, $http) {
  $scope.submit = function(form) {
    var scoreData = angular.toJson(form)
    $http.post('/bus_test', scoreData)
    .success(function (data) {
      console.log(scoreData)
    });
  };
 }]);
