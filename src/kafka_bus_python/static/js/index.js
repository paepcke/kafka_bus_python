app = angular.module('ScorePoster', [])

app.controller('FormControl', ['$scope', '$http', function($scope, $http) {
  $scope.scores = [];
  $scope.names = [];
  $scope.submit = function(form) {
    var scoreData = angular.toJson(form);
    $http.post('/bus_test', scoreData)
    .success(function (response) {
      $scope.scores.push(parseInt(response.score));
      $scope.names.push(response.uid);
    });
  };
}]);

app.directive('scorelist', function() {
  return {
    template: 'Names: {{names}}, Scores: {{scores}}'
  };
});
