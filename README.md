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
python3 -c "from openwakeword.utils import download_models; download_models(['hey_jarvis'], target_directory='/home/daikai/terminal_voice_client/models')"
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
  "device": 15,
  "threshold": 0.5,
  "timeout": 180,
  "_help": {
    "wake_word": "Wake word model trong thư mục models. Có thể dùng: hey_jarvis, alexa, hey_mycroft, hey_rhasspy, timer hoặc weather.",
    "device": "Index hoặc tên input device từ --list-devices. Máy hiện tại dùng 15 cho PipeWire/BY Y01.",
    "threshold": "Ngưỡng nhận diện từ 0.0 đến 1.0; thấp dễ kích hoạt hơn, cao ít nhận nhầm hơn.",
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

- `device`: index hoặc tên thiết bị thu âm. Dùng `python3 voice_client.py
  --list-devices` để xem danh sách. Index có thể thay đổi sau khi khởi động lại.
- `threshold`: ngưỡng nhận diện wake word từ `0.0` đến `1.0`. Giảm giá trị nếu
  khó đánh thức; tăng giá trị nếu chương trình thường xuyên nhận nhầm. Nên bắt
  đầu bằng `0.5`.
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

Xem danh sách micro rồi chọn bằng tên hoặc index:

```bash
python3 voice_client.py --list-devices
python3 voice_client.py --device 2
```

Trên máy dùng PipeWire, nên chọn thiết bị `pipewire` thay vì thiết bị ALSA vật
lý. PipeWire sẽ tự chuyển đổi âm thanh sang định dạng 16 kHz mono mà client yêu
cầu. Ví dụ trên máy hiện tại, thiết bị `pipewire` có index `15` và sử dụng micro
mặc định của hệ thống (BY Y01). Index có thể thay đổi sau khi khởi động lại, vì
vậy hãy kiểm tra lại bằng `--list-devices` trước khi chạy.

Không nên chọn trực tiếp BY Y01 bằng `--device 4` trên máy này vì thiết bị ALSA
vật lý không hỗ trợ trực tiếp tần số lấy mẫu 16 kHz.

Thứ tự ưu tiên cấu hình là: tham số dòng lệnh, biến môi trường, `config.json`,
sau đó là giá trị mặc định. Các biến môi trường tương ứng:
`VOICE_SERVER_URL`, `VOICE_API_KEY`, `VOICE_LANGUAGE`, `VOICE_SESSION_ID`,
`WAKE_WORD`, `WAKE_THRESHOLD`, `MIC_DEVICE`.

Các wake-word model có sẵn tùy phiên bản openWakeWord, thường gồm `hey_jarvis`, `alexa` và `hey_mycroft`. Một cụm tiếng Việt tùy ý cần model openWakeWord đã được huấn luyện; truyền đường dẫn model đó qua `--wake-word`.
