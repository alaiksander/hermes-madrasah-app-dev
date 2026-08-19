import 'dart:async';
import 'dart:html' as html;
import 'dart:typed_data';

/// File sing dipilih — dipakai bareng ing web & native.
class PickedFile {
  final String name;
  final Uint8List bytes;
  PickedFile(this.name, this.bytes);
}

/// Web: pilih file spreadsheet (xlsx/xls) nganggo input element dhewe (dart:html).
///
/// Penting: input TETEP ana ing DOM nganti selesai maca file —
/// file_picker mbusak input sakwise click() sing nyebabke dialog
/// Pilih file Excel (import murid/guru).
Future<PickedFile?> pickXlsxFile() => pickFile([
      '.xlsx',
      '.xls',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
    ]);

/// Pilih file CSV (legacy — import murid/guru lawas).
Future<PickedFile?> pickCsvFile() => pickFile(['.csv', 'text/csv']);

/// Pilih file JSON (restore backup tenant).
Future<PickedFile?> pickJsonFile() => pickFile(['.json', 'application/json']);

/// Pilih file gambar (logo platform).
Future<PickedFile?> pickImageFile() =>
    pickFile(['.png', '.jpg', '.jpeg', '.webp', 'image/png', 'image/jpeg', 'image/webp']);

/// Pilih file kanthi accept tartamtu (web: input element manual — andal ing Firefox).
Future<PickedFile?> pickFile(List<String> accepts) async {
  final completer = Completer<PickedFile?>();
  final input = html.FileUploadInputElement()
    ..accept = accepts.join(',')
    ..style.display = 'none';

  html.document.body!.children.add(input);
  var done = false;

  input.onChange.listen((_) {
    final files = input.files;
    if (files == null || files.isEmpty) {
      done = true;
      input.remove();
      completer.complete(null);
      return;
    }
    final file = files.first;
    final reader = html.FileReader();
    reader.onLoadEnd.listen((_) {
      done = true;
      input.remove();
      completer.complete(PickedFile(file.name, reader.result as Uint8List));
    });
    reader.onError.listen((_) {
      done = true;
      input.remove();
      completer.complete(null);
    });
    reader.readAsArrayBuffer(file);
  });

  // Deteksi cancel: fokus bali menyang window tanpa change event
  html.window.onFocus.first.then((_) {
    Future.delayed(const Duration(milliseconds: 800), () {
      if (!done && !completer.isCompleted) {
        done = true;
        input.remove();
        completer.complete(null);
      }
    });
  });

  input.click();
  return completer.future;
}
