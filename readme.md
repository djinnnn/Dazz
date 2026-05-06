
# Dazz++: Runtime-Feedback-Guided Browser Fuzzer

A browser fuzzer that combines grammar-based HTML generation with runtime-feedback-driven JavaScript fuzzing.

## Requirements

- **Operating System**: Linux (Ubuntu 20.04+) or macOS
- **Python**: 3.8+
- **Dependencies**: `pip3 install selenium==3.141.0 urllib3==1.26.5`

## Installation

```shell
git clone <repo-url> dazz
cd dazz
pip3 install selenium==3.141.0 urllib3==1.26.5
```

## Usage

### Basic Fuzzing

```shell
python3 main.py -b <browser> -p <parallel> -o <output_dir> [options]
```

### Options

| Option | Description | Default |
|---|---|---|
| `-b` / `--browser` | Target browser: `webkitgtk`, `webkit`, `chromium`, `firefox`, `safari` | `webkitgtk` |
| `-p` / `--parallel` | Number of parallel instances | `1` |
| `-o` / `--output_dir` | Output directory for crashes | *(required)* |
| `-t` / `--timeout` | Per-test timeout (ms) | `10000` |
| `-e` / `--time_to_exit` | Stop after N hours | - |
| `-x` / `--execution_iteration` | Stop after N iterations | - |

### Example

```shell
python3 main.py -b chromium -p 2 -o ./output -e 24
```

### Verify & Minimize Crashes

```shell
# Verify a crash
python3 crash_verify.py -b chromium -i crash.html -n 10

# Minimize a crash
python3 crash_minimize.py -b chromium -i crash.html -n 10
```
