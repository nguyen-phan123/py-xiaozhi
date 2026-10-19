# Domain Localization & Vocabulary Invariant

## Core Invariant
Every log message, CLI print, GUI label, error string, and commit/doc text MUST strictly adhere to the canonical terms in `CONTEXT.md`.

## Forbidden Terminology Mapping
| Canonical Term (`Keep`) | Forbidden Term (`Drop`) | Context / Component |
|---|---|---|
| **Mã xác thực** | Mã kích hoạt, 验证码, OTP, Verification pin | Onboarding verification code in UI/logs |
| **Kích hoạt** | 激活, Đăng ký, Cấp quyền | Device binding workflow |
| **Chờ lệnh** | 待命, Rảnh rỗi, Đang nghỉ | Device idle / listening state |

## Enforcement Checklist for Edits & Code Review
1. **Pre-check**: Consult `CONTEXT.md` before writing or translating any UI or log string.
2. **Zero Synonyms**: Reject synonyms listed in the `_Avoid_` section of `CONTEXT.md`.
3. **Log Audit**: Ensure log statements (e.g. `logger.info`, `logger.error`) never introduce colloquial terms.
