# Configurable local wake detection

## Configure without starting the desktop

From an installed environment or the checkout:

```bash
python -m ultron wake-config
python -m ultron wake-config --model alexa --threshold 0.6
python -m ultron wake-config --model hey_jarvis --threshold 0.5
```

The `ultron wake-config` console command is equivalent after package installation.
Restart the assistant after changes. The running detector snapshots its selection;
there is no hot model replacement. Setting the configuration does not install
packages, download models, enable microphone gating, or start the assistant.
The existing WAKE WORD UI control remains the explicit opt-in setup/enable action.
Its tooltip shows the configured label; native UI behavior still needs testing.

Supported builtin IDs: `hey_jarvis`, `alexa`, `hey_mycroft`, `timer`, `weather`.
Availability/download compatibility depends on the installed openwakeword release.
The immutable backward-compatible default constant remains `hey_jarvis`, and the
actual default spoken phrase is **hey jarvis**, NOT hey ultron. No model is renamed.
Unknown IDs/phrases are rejected rather than silently falling back to another model.

Settings are saved in the existing deployment `config/api_keys.json`:

```json
{
  "wake_word_enabled": false,
  "wake_word_model": "hey_jarvis",
  "wake_word_threshold": 0.5,
  "wake_word_label": "hey jarvis"
}
```

Threshold must be a finite number greater than zero and at most one; booleans are
not numbers here. Labels are printable 1–80 character display text, not audio
models. Changing a model through the CLI clears an old label unless a new one is
supplied. Existing unrelated configuration fields/credentials are preserved. The
CLI refuses corrupt JSON rather than overwriting it, validates before mutation,
and writes through a private temporary file plus atomic replacement. This is not
a concurrent configuration transaction: don't edit the same config simultaneously
in the running UI/another process. Atomic replacement may change file permissions
(to the private tempfile defaults); filesystem/parent-directory trust still applies.
The older shared runtime configuration reader retains its existing missing/bad-JSON
default behavior; this change is not a rewrite of all configuration storage.

## Custom phrase

A text field cannot train a phrase. Obtain/train a compatible trusted openwakeword
ONNX model first, then use an absolute existing path:

```bash
python -m ultron wake-config --model /absolute/path/my_wake.onnx --label "hello assistant" --threshold 0.65
```

Windows example: `--model "C:\Models\my_wake.onnx"`. Custom models require compatible
openwakeword plus its ONNX melspectrogram/embedding feature resources, manually
provisioned in that environment. The UI setup helper does not guess a URL, fetch
arbitrary custom models or download all pretrained models as a fallback. It reports
unavailable if custom prerequisites are missing. TFLite-only resources do not count
as ready because this detector loads the ONNX framework. File presence is a cheap
readiness check, NOT proof that a model is valid or will recognize the advertised
phrase; actual loading can fail. Treat model files and dependencies as trusted
native inference inputs; there is no ONNX security sandbox or model signature check.
A custom model's returned prediction key must match its filename stem (or a supported
`_v<number>` suffix); incompatible providers must be adapted explicitly, not by
accepting unrelated model scores.

Builtin setup downloads only the selected builtin through the upstream helper.
There is no old-signature fallback that downloads all models. Existing setup still
uses pip/network when explicitly requested in the UI; no real install/download was
performed during tests. Readiness requires ONNX feature files plus the selected
model; another model's high score no longer wakes the assistant. Malformed/out-of-range
scores are not treated as positive detections. A threshold is a tuning value, not a
measured false-activation guarantee. Microphone, native inference, latency, device
selection, false positives and Windows UI have not been certified in this sandbox.
Use WAKE NOW when wake detection is unavailable.
