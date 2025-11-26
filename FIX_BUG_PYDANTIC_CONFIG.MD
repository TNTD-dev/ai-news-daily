# Fix Bug: Pydantic Settings không parse được `List[str]` từ CSV string

## 🐛 Hiện tượng lỗi

```python
# Config
youtube_channels: List[str] = Field(alias="YOUTUBE_CHANNELS")

# .env file
YOUTUBE_CHANNELS=channel1,channel2,channel3
```

**Kết quả:**
```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
error parsing value for field "youtube_channels"
```

---

## 🔍 Nguyên nhân

### Flow gây lỗi:
```
1. pydantic-settings đọc env var → "channel1,channel2"
2. Thấy type hint List[str] → "Đây là JSON array!"
3. Gọi json.loads("channel1,channel2") → ❌ LỖI
4. Validator mode="before" không được gọi (lỗi xảy ra trước đó)
```

### Điểm mấu chốt:
- **pydantic-settings** tự động parse JSON khi gặp `List`, `Dict`, etc.
- Parsing xảy ra **TRƯỚC** validator `mode="before"`
- CSV string không phải JSON hợp lệ → lỗi ngay

---

## ✅ Giải pháp: `@computed_field`

### Code mới:

```python
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings

class ScrapingConfig(BaseSettings):
    # ✅ Lưu raw string (internal field)
    _youtube_channels_raw: str = Field(
        default="",
        alias="YOUTUBE_CHANNELS"
    )
    
    # ✅ Expose parsed list (computed property)
    @computed_field
    @property
    def youtube_channels(self) -> List[str]:
        """Parse CSV string thành list lúc runtime"""
        if not self._youtube_channels_raw.strip():
            return []
        return [
            ch.strip() 
            for ch in self._youtube_channels_raw.split(",") 
            if ch.strip()
        ]
```

### Cách dùng (không đổi):
```python
config = ScrapingConfig()
for channel in config.youtube_channels:  # ✅ Vẫn là List[str]
    print(channel)
```

---

## 🎯 Tại sao cách này work?

| Bước | Điều gì xảy ra | Kết quả |
|------|----------------|---------|
| 1. pydantic-settings parse | Thấy `_youtube_channels_raw: str` | ✅ Lưu string, không parse JSON |
| 2. Access `config.youtube_channels` | Gọi `@computed_field` property | ✅ Parse CSV → List lúc runtime |
| 3. Type checking | IDE thấy return type `List[str]` | ✅ Type safe, autocomplete work |

**Công thức:**
```
Storage (str) + Computed Property = Type-safe List
```

---

## 📝 Các bước sửa code

### 1. Thêm import
```python
from pydantic import EmailStr, Field, field_validator, computed_field
```

### 2. Đổi field declaration
```python
# ❌ Cũ
youtube_channels: List[str] = Field(
    default_factory=list,
    alias="YOUTUBE_CHANNELS"
)

# ✅ Mới
_youtube_channels_raw: str = Field(
    default="",
    alias="YOUTUBE_CHANNELS"
)
```

### 3. Thêm computed property
```python
@computed_field
@property
def youtube_channels(self) -> List[str]:
    if not self._youtube_channels_raw.strip():
        return []
    return [ch.strip() for ch in self._youtube_channels_raw.split(",") if ch.strip()]
```

### 4. Xóa validator cũ
```python
# ❌ Xóa method này
@field_validator("youtube_channels", mode="before")
def parse_youtube_channels(cls, v): ...
```

---

## 🆚 So sánh approaches

| Approach | Parse CSV? | Type safe? | Kết quả |
|----------|-----------|------------|---------|
| `List[str]` + validator | ❌ JSON error | - | **LỖI** |
| `str` + validator return List | ✅ | ❌ Type conflict | **LỖI** |
| `str` + `@computed_field` | ✅ | ✅ | **✅ WORK** |

---

## 💡 Ưu điểm của `@computed_field`

✅ **Tách biệt storage vs interface**
- Storage: raw string từ env
- Interface: parsed list cho code

✅ **Type safe hoàn toàn**
- IDE autocomplete
- Type checker hoạt động
- Return type rõ ràng

✅ **Lazy evaluation**
- Chỉ parse khi cần dùng
- Tiết kiệm performance

✅ **Framework-friendly**
- Không fight với pydantic-settings
- Follow best practices

✅ **Dễ extend logic**
```python
@computed_field
@property
def youtube_channels(self) -> List[str]:
    channels = self._youtube_channels_raw.split(",")
    # Có thể thêm filter, validation, transformation
    return [ch for ch in channels if ch.startswith("UC")]
```

---

## 📌 Nhớ nhanh

```
Lỗi: List[str] → pydantic-settings parse JSON → boom!
Fix:  str (storage) + @computed_field (interface) = win!
```

**Pattern:**
1. Internal field: `_raw_data: str`
2. Public property: `@computed_field` parse → `List`
3. User không biết gì, vẫn dùng như cũ

---

## 🔧 .env file không đổi

```bash
# Vẫn dùng CSV format như bình thường
YOUTUBE_CHANNELS=channel1,channel2,channel3

# Hoặc để trống
YOUTUBE_CHANNELS=
```

---

## ⚠️ Lưu ý

- `@computed_field` cần Pydantic v2+
- Field internal bắt đầu `_` để tránh export
- Property tính mỗi lần access (nếu cần cache, dùng `@cached_property`)

---

## 🎓 Bài học

**Khi dùng pydantic-settings với complex types:**
1. Hiểu parsing order: env source → validation → field
2. `mode="before"` không cứu được JSON parsing errors
3. Dùng simple types (str, int) cho storage
4. Dùng `@computed_field` cho transformations
5. Tách concerns: storage ≠ interface