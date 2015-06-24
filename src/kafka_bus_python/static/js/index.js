app = angular.module('ScorePoster', [])

// FormControl controller handles form submission AJAX calls and callback
app.controller('FormControl', ['$scope', '$http', function($scope, $http) {
  $scope.grades = [];
  $scope.names = [];
  $scope.submit = function(form) {
    var scoreData = angular.toJson(form);
    $http.post('/bus_test', scoreData)
    .success(function (response) {
      $scope.grades.push(response.grade);
      $scope.names.push(response.uid);
    });
  };
}]);

// <scorelist> element provides user with log of uids and scores.
// NOTE: Not used currently
app.directive('scorelist', function() {
  return {
    template: 'Names: {{names}}, Scores: {{grades}}'
  };
});
