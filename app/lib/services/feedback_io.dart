import 'package:flutter/services.dart';

/// Feedback native (Android/iOS): haptic + system sound.
void successFeedback() {
  HapticFeedback.mediumImpact();
  SystemSound.play(SystemSoundType.click);
}

void errorFeedback() {
  HapticFeedback.vibrate();
}
