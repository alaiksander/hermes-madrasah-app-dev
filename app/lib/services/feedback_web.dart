import 'dart:js_interop';

/// JS function sing dipasang ing web/index.html (madrasahBeep).
@JS('madrasahBeep')
external void _madrasahBeep(bool success);

/// Feedback web:
/// - beep: WebAudio oscillator (Firefox + Chrome)
/// - vibrate: navigator.vibrate (Firefox/Chrome Android; no-op ing desktop)
void successFeedback() {
  _madrasahBeep(true);
}

void errorFeedback() {
  _madrasahBeep(false);
}
