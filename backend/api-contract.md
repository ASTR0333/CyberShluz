# API Contract (Шлюз оркестрации)

## 1. Выделение стенда (Deploy)
**POST** `/api/v1/deploy`

**Request Body:**
```json
{
  "user_id": "string (LMS User ID)",
  "lab_id": "integer",
  "role": "string (student/teacher)"
}
```

**Response (202 Accepted):**
```json
{
  "stand_id": "uuid",
  "project_id": "uuid",
  "status": "PENDING",
  "message": "В очереди на развертывание"
}
```

## 2. Статус стенда (Status)
**GET** `/api/v1/status/{stand_id}`

**Response (200 OK):**
```json
{
  "stand_id": "uuid",
  "status": "READY",
  "ip_address": "192.168.1.10",
  "expires_at": "2026-05-18T14:00:00Z",
  "frozen_until": null
}
```
*Возможные статусы:* `PENDING`, `DEPLOYING`, `READY`, `FREEZE`, `CLEANING`, `FREE`

## 3. Заморозка стенда (Freeze) - Техподдержка
**POST** `/api/v1/freeze/{stand_id}`

**Request Body:**
```json
{
  "reason": "string"
}
```

**Response (200 OK):**
```json
{
  "stand_id": "uuid",
  "status": "FREEZE",
  "frozen_until": "2026-05-19T12:00:00Z"
}
```

## 4. Проверка лабы (Check)
**POST** `/api/v1/check/{stand_id}`

**Response (202 Accepted):**
```json
{
  "stand_id": "uuid",
  "check_task_id": "uuid",
  "status": "CHECKING"
}
```

## 5. Результат проверки
**GET** `/api/v1/check/{check_task_id}/result`

**Response (200 OK):**
```json
{
  "status": "PASSED",
  "log": "Успешно: Порт 80 открыт. Успешно: nginx установлен."
}
```

## 6. Удаление/Очистка стенда (Cleanup)
**POST** `/api/v1/cleanup/{stand_id}`

**Response (202 Accepted):**
```json
{
  "stand_id": "uuid",
  "status": "CLEANING"
}
```

## 7. Добавление личного SSH-ключа на Linux-ВМ
**POST** `/api/v1/stand/{stand_id}/pubkey`

Публичный ключ устанавливается пользователю `student` на все ВМ стенда, роль
которых начинается с `L`. Для внутренних ВМ backend подключается через L-MS.

## 8. Веб-консоль Windows-ВМ
**POST** `/api/v1/stand/{stand_id}/console/{vm_role}`

`vm_role` должна начинаться с `W`. В ответ возвращается ссылка на консоль
принадлежащего стенду инстанса в панели КИ.
