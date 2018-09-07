function customCellWriter(column, record, pos) {

  var html = column.attributeWriter(record),
      td = '<td';

  if (pos == 6){
    html = '...'
  }
  if (column.hidden || column.textAlign) {
    td += ' style="';

    // keep cells for hidden column headers hidden
    if (column.hidden) {
      td += 'display: none; ';
    }

    // keep cells aligned as their column headers are aligned
    if (column.textAlign) {
      td += 'text-align: center;';
    }

    td += '"';
  }

  return td + '>' + html + '</td>';
};


function customRowWriter(rowIndex, record, columns, cellWriter) {
  var tr = '';

  // grab the record's attribute for each column
  for (var i = 0, len = columns.length; i < len; i++) {
    tr += cellWriter(columns[i], record, i);
  }

  return '<tr>' + tr + '</tr>';
};
