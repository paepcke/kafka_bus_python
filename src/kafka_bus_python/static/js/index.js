/*
  $(document).ready(function () {
    $("#postbutton").click(function () {
      var msg = $("#poster").serialize();
      console.log(msg);
      $.post('http://localhost:5000/bus_test', msg);
    });
  });
*/

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
