$(document).ready(function() {
  $('thead th').each(function(index) {
    if (index == 0)
      var td = '<td></td>';
    else
      var td = '<td><input type="text" class="input-sm"/></td>';

    $('tfoot tr').append(td);
  });

  var table = $('#listings_table').DataTable({
    paging: false,
    columnDefs: [{ "orderable": false, "targets": 0 }],
    order: [],
    dom: 'ti',
  });

  $('tfoot').css('display', 'table-header-group');
  $('tfoot input').css('width', '100%');

  table.columns().every(function() {
    var that = this;
    $('input', this.footer()).on('keyup change', function() {
      if (that.search() !== this.value) {
        that.search(this.value, true, false).draw();
      }
    });
  });
});
