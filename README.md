# Terminal Voice Client

Client chạy trong terminal theo luồng:

`micro → wake word cục bộ → ghi âm đến khi im lặng → /v1/voice/chat → hiện text`

Âm thanh nền chỉ được xử lý tại máy. Client chỉ gửi câu hỏi sau khi wake word được nhận diện. Một `session_id` được giữ nguyên trong suốt tiến trình nên server tiếp tục hội thoại từ các lượt trước.

## Cài đặt

Các bước dưới đây cài trực tiếp cho tài khoản người dùng, không dùng môi trường
ảo và không chạy `install.sh`.

### 1. Cài Python, pip và PortAudio

```bash
sudo apt update
sudo apt install -y python3 python3-pip libportaudio2 portaudio19-dev
```

### 2. Chuyển vào thư mục client

```bash
cd /home/daikai/terminal_voice_client
```

### 3. Cài các thư viện Python

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 -m pip install --user --break-system-packages --no-deps openwakeword==0.6.0
```

Client dùng ONNX Runtime nên không cần cài `tflite-runtime`. Tùy chọn
`--break-system-packages` là cần thiết trên các bản Ubuntu mới; các package vẫn
được cài trong thư mục người dùng nhờ `--user`.

### 4. Tải model vào thư mục của dự án

```bash
mkdir -p /home/daikai/terminal_voice_client/models
python3 -c "from openwakeword.utils import download_models; download_models(['hey_jarvis'], target_directory='~/terminal_voice_client/models')"
```

Kiểm tra các model đã tải:

```bash
ls -lh /home/daikai/terminal_voice_client/models
```

Thư mục phải có tối thiểu các file ONNX sau:

```text
models/embedding_model.onnx
models/melspectrogram.onnx
models/hey_jarvis_v0.1.onnx
```

### 5. Kiểm tra thư viện

```bash
python3 -c "import numpy, onnxruntime, openwakeword, requests, sounddevice; print('Cài đặt thành công')"
```

## Chạy

### 1. Cấu hình client

Mở `/home/daikai/terminal_voice_client/config.json` và cập nhật các giá trị:

```json
{
  "server": "http://192.168.1.10:8000",
  "api_key": "YOUR_KEY",
  "wake_word": "hey_jarvis",
  "language": "en",
  "session_id": "phong-khach",
  "device": "pipewire",
  "threshold": 0.5,
  "silence_seconds": 2.5,
  "silence_multiplier": 2.0,
  "min_silence_rms": 100.0,
  "timeout": 180,
  "_help": {
    "wake_word": "Wake word model trong thư mục models. Có thể dùng: hey_jarvis, alexa, hey_mycroft, hey_rhasspy, timer hoặc weather.",
    "device": "Dùng pipewire để thu từ input mặc định của PipeWire và tự chuyển đổi sang 16 kHz mono. Chọn micro vật lý bằng wpctl set-default SOURCE_ID.",
    "threshold": "Ngưỡng nhận diện từ 0.0 đến 1.0; thấp dễ kích hoạt hơn, cao ít nhận nhầm hơn.",
    "silence_seconds": "Số giây im lặng liên tục trước khi gửi audio.",
    "silence_multiplier": "Hệ số ngưỡng giọng nói so với tiếng ồn nền.",
    "min_silence_rms": "Ngưỡng RMS tối thiểu để coi là giọng nói.",
    "timeout": "Số giây tối đa chờ server trả lời."
  }
}
```

Thay `YOUR_KEY` bằng API key thật. Nếu server không yêu cầu API key, đặt giá trị
thành chuỗi rỗng: `"api_key": ""`.

### 2. Chạy client

Khởi động `voice_ai_server`, sau đó chạy:

```bash
cd /home/daikai/terminal_voice_client
python3 voice_client.py
```

Chương trình tự đọc `config.json` trong cùng thư mục với `voice_client.py`.
Tham số dòng lệnh vẫn có thể dùng để ghi đè tạm thời một giá trị trong file.

Object `_help` chỉ chứa hướng dẫn và được chương trình bỏ qua. Ý nghĩa các cấu
hình âm thanh quan trọng:

- `device`: thiết bị mà client mở. Khuyến nghị dùng tên `pipewire`; sau đó chọn
  micro vật lý mặc định bằng `wpctl` như hướng dẫn bên dưới. Không nên lưu index
  thiết bị vì index có thể thay đổi sau khi khởi động lại.
- `threshold`: ngưỡng nhận diện wake word từ `0.0` đến `1.0`. Giảm giá trị nếu
  khó đánh thức; tăng giá trị nếu chương trình thường xuyên nhận nhầm. Nên bắt
  đầu bằng `0.5`.
- `silence_seconds`: số giây im lặng liên tục trước khi client kết thúc câu và
  gửi audio. Tăng giá trị này nếu câu bị gửi khi bạn chỉ đang tạm dừng. Giá trị
  khuyến nghị ban đầu là `2.5`.
- `silence_multiplier`: hệ số nhân với mức tiếng ồn nền để xác định giọng nói.
  Giảm nhẹ nếu lời nói nhỏ bị coi là im lặng. Giá trị mặc định là `2.0`.
- `min_silence_rms`: ngưỡng âm lượng tối thiểu để xác định giọng nói. Giảm nếu
  micro hoặc giọng nói nhỏ; giảm quá thấp có thể khiến tiếng ồn giữ bản ghi mở.
  Giá trị mặc định là `100.0`.
- `timeout`: thời gian tối đa, tính bằng giây, chờ voice server trả lời cho mỗi
  câu hỏi. `180` tương đương 3 phút.

### Đổi wake word

Các wake word chuẩn của openWakeWord 0.6.0 gồm `hey_jarvis`, `alexa`,
`hey_mycroft`, `hey_rhasspy`, `timer` và `weather`. Tải model mong muốn vào thư
mục dự án, ví dụ tải `alexa`:

```bash
python3 -c "from openwakeword.utils import download_models; download_models(['alexa'], target_directory='/home/daikai/terminal_voice_client/models')"
```

Sau đó sửa trong `config.json`:

```json
"wake_word": "alexa"
```

### Chọn microphone

Client cần âm thanh 16 kHz mono. Micro BY Y01 chỉ hỗ trợ trực tiếp 44.1/48 kHz
stereo, vì vậy không chọn thiết bị ALSA vật lý như `BY Y01: USB Audio (hw:2,0)`
trong `config.json`. Hãy để PipeWire thu từ BY Y01 và chuyển đổi định dạng cho
client:

```json
"device": "pipewire"
```

Xem các thiết bị mà client có thể mở:

```bash
python3 voice_client.py --list-devices
```

Xem các nguồn thu của PipeWire:

```bash
wpctl status
```

Trong mục `Sources`, dấu `*` chỉ micro đang được dùng mặc định. Ví dụ:

```text
Sources:
  * 50. BY Y01 Analog Stereo
    53. Family 17h/19h HD Audio Controller Analog Stereo
```

Nếu BY Y01 chưa có dấu `*`, dùng ID được hiển thị trên chính máy đó để chọn nó:

```bash
wpctl set-default 50
```

ID `50` chỉ là ví dụ và có thể thay đổi. Kiểm tra chính xác nguồn mặc định sau
khi chọn:

```bash
wpctl inspect @DEFAULT_AUDIO_SOURCE@ | grep -E 'alsa.card_name|node.description|node.name'
```

Khi BY Y01 được chọn, kết quả sẽ chứa `BY Y01` và một node tương tự
`alsa_input.usb-BY_BY_Y01...`. Sau đó chạy client bình thường hoặc kiểm tra tạm
thời mà không sửa cấu hình:

```bash
python3 voice_client.py --device pipewire
```

Đường đi của âm thanh lúc này là:

```text
BY Y01 (44.1/48 kHz stereo) → PipeWire → client (16 kHz mono)
```

Nếu rút BY Y01, PipeWire có thể chuyển sang micro tích hợp đang khả dụng. Chạy
`wpctl status` để biết micro nào đang có dấu `*` trước khi khởi động client.

Nếu mở trực tiếp BY Y01 bằng index ALSA, client sẽ báo `paInvalidSampleRate` vì
thiết bị vật lý không nhận trực tiếp định dạng 16 kHz mono mà client yêu cầu.

Thứ tự ưu tiên cấu hình là: tham số dòng lệnh, biến môi trường, `config.json`,
sau đó là giá trị mặc định. Các biến môi trường tương ứng:
`VOICE_SERVER_URL`, `VOICE_API_KEY`, `VOICE_LANGUAGE`, `VOICE_SESSION_ID`,
`WAKE_WORD`, `WAKE_THRESHOLD`, `MIC_DEVICE`, `VOICE_SILENCE_SECONDS`,
`VOICE_SILENCE_MULTIPLIER`, `VOICE_MIN_SILENCE_RMS`.

Các wake-word model có sẵn tùy phiên bản openWakeWord, thường gồm `hey_jarvis`, `alexa` và `hey_mycroft`. Một cụm tiếng Việt tùy ý cần model openWakeWord đã được huấn luyện; truyền đường dẫn model đó qua `--wake-word`.
