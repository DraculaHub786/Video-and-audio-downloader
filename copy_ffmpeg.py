import imageio_ffmpeg, shutil, os
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
shutil.copy(ffmpeg_path, "ffmpeg.exe")
print(f"Copied {ffmpeg_path} to ffmpeg.exe")
# We also need ffprobe. For audio extraction and format merging, ffprobe is usually needed by yt-dlp.
# However, imageio-ffmpeg doesn't come with ffprobe.
# yt-dlp can merge video/audio without ffprobe if explicitly told to only merge.
# We will just depend on ffmpeg.
