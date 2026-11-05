# تشغيل المساعد على سيرفر (Docker)

هاي الخطوات لتشغيل المساعد على سيرفر Linux (مثل DigitalOcean أو Hetzner) بحيث يكون شغّال 24 ساعة.

## اللي بتحتاجه

- سيرفر **Ubuntu** (أرخص خطة بتكفي، مثلاً 2GB RAM)
- **دومين** (مثلاً `assistant.almustaqbal.com`)
- مفتاح **Groq**

## 1. وجّه الدومين للسيرفر

من لوحة تحكم الدومين، اعمل سجل **A** باسم الدومين، وحط فيه **IP السيرفر**.

## 2. ادخل على السيرفر وثبّت Docker

```bash
ssh root@IP-السيرفر
curl -fsSL https://get.docker.com | sh
```

## 3. نزّل المشروع من GitHub

```bash
git clone https://github.com/Aseel-Gharaibeh12/CallCenterAi.git
cd CallCenterAi
```

## 4. اعمل ملف الإعدادات

```bash
cp .env.example .env
nano .env
```

عبّي القيم الثلاث:

- `GROQ_API_KEY`: مفتاح Groq
- `ADMIN_PASSWORD`: كلمة سر لصفحة المكالمات (**ضرورية على السيرفر**)
- `DOMAIN`: الدومين تبعك

للحفظ اضغط **Ctrl + O** ثم **Enter**، وللخروج **Ctrl + X**.

## 5. شغّل

```bash
docker compose up -d --build
```

أول مرة بتاخذ كم دقيقة. بعدها افتح:

- المساعد: `https://الدومين/app/`
- المكالمات: `https://الدومين/admin` (أي اسم مستخدم + كلمة السر من `.env`)

## أوامر مفيدة

| بدك | الأمر |
|---|---|
| تشوف شو عم يصير (السجل) | `docker compose logs -f bot` |
| تعيد التشغيل بعد تعديل `company_info.txt` | `docker compose restart bot` |
| تحدّث من GitHub | `git pull && docker compose up -d --build` |
| توقف كل شي | `docker compose down` |

المكالمات المحفوظة موجودة بمجلد `conversations` على السيرفر.

## إذا الصفحة فتحت بس الصوت ما اشتغل

- **جدار الحماية (Firewall):** إذا مفعّل على السيرفر، لازم تسمح بـ:
  - المنافذ **80** و **443** (TCP) للصفحة
  - منافذ **UDP** للصوت (مثلاً `sudo ufw allow 1024:65535/udp`)
- **شبكات مقيّدة:** بعض شبكات الشركات أو الموبايل بتمنع الاتصال المباشر. الحل إضافة سيرفر **TURN**، وهاي خطوة متقدمة نعملها إذا احتجناها.
