(function () {
  var toggles = document.querySelectorAll('[data-bs-toggle="tab"], [data-bs-toggle="pill"]');
  if (!toggles.length || !window.bootstrap) return;

  function targetId(el) {
    var target = el.getAttribute('data-bs-target') || el.getAttribute('href') || '';
    return target.replace('#', '');
  }

  var wanted = new URLSearchParams(window.location.search).get('tab');
  if (wanted) {
    for (var i = 0; i < toggles.length; i++) {
      if (targetId(toggles[i]) === wanted) {
        bootstrap.Tab.getOrCreateInstance(toggles[i]).show();
        break;
      }
    }
  }

  toggles.forEach(function (toggle) {
    toggle.addEventListener('shown.bs.tab', function (event) {
      var id = targetId(event.target);
      if (!id) return;
      var params = new URLSearchParams(window.location.search);
      params.set('tab', id);
      history.replaceState(null, '', window.location.pathname + '?' + params.toString() + window.location.hash);
    });
  });
})();
