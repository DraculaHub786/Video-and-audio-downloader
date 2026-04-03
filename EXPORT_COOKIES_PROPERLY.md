# ⚠️ How to Export YouTube Cookies Properly

## Problem: "cookies are no longer valid" or "have been rotated"

YouTube automatically rotates cookies when:
- You log out and back in
- You open a new browser session
- You close and reopen the browser
- Security checks trigger

## ✅ Correct Export Procedure

Follow these steps **exactly** to avoid cookie rotation:

### 1. Prepare Your Browser (DO NOT SKIP)

**Before exporting:**
1. Open YouTube.com in a **private/incognito window**
2. Sign in to YouTube
3. Watch a video to confirm you're logged in
4. **Keep this window open** — don't close it!

### 2. Install Cookie Extension

Use one of these:
- **Chrome/Edge**: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- **Firefox**: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

### 3. Export Cookies (Critical Steps)

**In the SAME browser window where you're logged in:**

1. Click the cookie extension icon
2. Click "Export" or "Download"
3. Save as `youtube_cookies.txt`
4. **Do NOT:**
   - Close the browser
   - Log out of YouTube
   - Open a new browser session
   - Clear cookies

### 4. Convert & Deploy Immediately

**Within 5 minutes of export:**

```powershell
cd "C:\Users\afjal\Documents\Mini-Projects\video & audio downloader"
.\convert_cookies.ps1
```

Then immediately update Render (don't wait).

### 5. Verify Cookies Are Fresh

**Test locally first:**

```powershell
# Set env var temporarily
$env:YOUTUBE_COOKIES_BASE64 = (Get-Clipboard)

# Run app
python app.py
```

Visit `http://localhost:5000` and test a YouTube video.

If it works locally, **then** update Render.

---

## 🔄 Cookie Lifespan

YouTube cookies typically last:
- **With active session**: 1-6 months
- **After browser close**: May rotate immediately
- **After logout**: Expire instantly

**Best practice**: Export fresh cookies every 2-4 weeks.

---

## 🐛 Troubleshooting

### "Cookies are no longer valid" immediately after export

**Cause**: You logged out, closed browser, or opened new session.

**Fix**:
1. Open **incognito/private window**
2. Sign in to YouTube
3. Export cookies **without closing window**
4. Deploy immediately

### "Skipping client 'android' since it does not support cookies"

**This is now fixed** — the app uses `web` client when cookies are present.

### Cookies work locally but not on Render

**Causes**:
1. Cookies expired between local test and Render update
2. Base64 corruption during copy-paste

**Fix**:
1. Export fresh cookies
2. Update Render **immediately** (within 5 minutes)
3. Don't copy-paste between sessions

---

## ✅ Success Checklist

Before deploying to Render:

- [ ] Exported cookies from **private/incognito window**
- [ ] YouTube session is **still active** in browser
- [ ] Tested **locally first** with `$env:YOUTUBE_COOKIES_BASE64`
- [ ] Local test **succeeded**
- [ ] Deploying to Render **within 5 minutes** of export
- [ ] Not logging out until Render deployment completes

---

## 🎯 Quick Reference

**Good workflow:**
1. Incognito window → Sign in to YouTube
2. Export cookies (keep window open)
3. Test locally immediately
4. Deploy to Render immediately
5. Verify `/health` shows cookies loaded
6. Test YouTube download
7. Close incognito window

**Bad workflow:**
1. Export cookies
2. Close browser ❌
3. Come back next day ❌
4. Deploy to Render ❌
5. Cookies already rotated ❌

---

## 📊 Expected Logs

**Good (cookies working):**
```
[INIT] ✓ YouTube cookies loaded from YOUTUBE_COOKIES_BASE64 (base64)
[youtube] Extracting URL: https://www.youtube.com/watch?v=...
[youtube] Downloading web player API JSON
```

**Bad (cookies invalid):**
```
WARNING: [youtube] The provided YouTube account cookies are no longer valid.
WARNING: [youtube] Skipping client "android" since it does not support cookies
```

---

## 🔐 Security Note

Cookies from **private/incognito sessions** are safer because:
- They expire when you close the window
- They're not tied to your main Google account session
- They're isolated from your regular browsing

**Recommended**: Use a dedicated Google account for YouTube downloads, not your personal account.
