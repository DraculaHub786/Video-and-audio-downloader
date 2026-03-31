# YouTube Cookies to Base64 Converter
# Run this script after exporting cookies from browser

$cookiesFile = "youtube_cookies.txt"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "YouTube Cookies → Base64 Converter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if file exists
if (-not (Test-Path $cookiesFile)) {
    Write-Host "❌ Error: youtube_cookies.txt not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please:" -ForegroundColor Yellow
    Write-Host "  1. Install browser extension: Get cookies.txt LOCALLY" -ForegroundColor Yellow
    Write-Host "  2. Go to YouTube.com (signed in)" -ForegroundColor Yellow
    Write-Host "  3. Click extension → Export" -ForegroundColor Yellow
    Write-Host "  4. Save as: youtube_cookies.txt" -ForegroundColor Yellow
    Write-Host "  5. Place in: $(Get-Location)" -ForegroundColor Yellow
    Write-Host "  6. Run this script again" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Read file
Write-Host "✓ Found youtube_cookies.txt" -ForegroundColor Green
$content = Get-Content $cookiesFile -Raw

# Validate format
if (-not $content.StartsWith("# Netscape HTTP Cookie File")) {
    Write-Host "⚠ Warning: File doesn't start with Netscape header" -ForegroundColor Yellow
    Write-Host "  This might not be a valid cookies.txt file" -ForegroundColor Yellow
    Write-Host ""
}

# Convert to base64
Write-Host "✓ Converting to base64..." -ForegroundColor Green
$bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
$base64 = [Convert]::ToBase64String($bytes)

# Copy to clipboard
$base64 | Set-Clipboard
Write-Host "✓ Copied to clipboard!" -ForegroundColor Green
Write-Host ""

# Display instructions
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Go to Render Dashboard:" -ForegroundColor White
Write-Host "   https://dashboard.render.com" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Select your video downloader service" -ForegroundColor White
Write-Host ""
Write-Host "3. Go to: Environment tab" -ForegroundColor White
Write-Host ""
Write-Host "4. Click: Add Environment Variable" -ForegroundColor White
Write-Host ""
Write-Host "5. Enter:" -ForegroundColor White
Write-Host "   Key:   YOUTUBE_COOKIES_BASE64" -ForegroundColor Yellow
Write-Host "   Value: " -ForegroundColor Yellow -NoNewline
Write-Host "<Paste with Ctrl+V>" -ForegroundColor Green
Write-Host ""
Write-Host "6. Click: Save Changes" -ForegroundColor White
Write-Host ""
Write-Host "7. Wait 2-3 minutes for auto-redeploy" -ForegroundColor White
Write-Host ""
Write-Host "8. Test your site - should work now! 🎉" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Show preview
Write-Host "Base64 Preview (first 100 chars):" -ForegroundColor Gray
Write-Host $base64.Substring(0, [Math]::Min(100, $base64.Length)) -ForegroundColor DarkGray
Write-Host "..." -ForegroundColor DarkGray
Write-Host ""
Write-Host "Length: $($base64.Length) characters" -ForegroundColor Gray
Write-Host ""

Write-Host "✅ Ready to paste in Render!" -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to exit"
