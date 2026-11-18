import gradio as gr
import subprocess
import os
import textwrap
from faster_whisper import WhisperModel

# Whisper model load karein (Hindi + English dono ke liye best)
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

def format_timestamp(seconds):
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

def transcribe_video(video_path):
    segments, _ = whisper_model.transcribe(video_path)
    return list(segments)

def generate_srt(segments, srt_path):
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = format_timestamp(seg.start)
            end = format_timestamp(seg.end)
            f.write(f"{i}\n{start} --> {end}\n{seg.text.strip()}\n\n")

def escape_ffmpeg_text(text):
    # FFmpeg drawtext ke special characters safe karne ke liye
    return text.replace(":", "\\:").replace("'", "").replace('"', "").replace("%", "\\%")

def process_video(
    input_video,
    # 1. Silence Cut Controls
    enable_silence_cut,
    silence_threshold,
    # 2. Vertical Crop Controls
    enable_vertical_crop,
    # 3. Auto Hook Controls
    enable_hook,
    hook_mode,
    custom_hook_text,
    enable_hook_zoom,
    enable_hook_sfx,
    hook_sfx_file,
    # 4. Auto Captions Controls
    enable_captions,
    caption_font_size,
    # 5. BGM Controls
    enable_bgm,
    bgm_file,
    bgm_volume
):
    if not input_video:
        return None, "Pehle ek raw video upload karein!"

    current_video = input_video
    log = ["🚀 Processing shuru ho rahi hai..."]

    try:
        # STEP 1: Silence Cut (ON/OFF)
        if enable_silence_cut:
            out_silence = "step1_silence.mp4"
            cmd = [
                "auto-editor", current_video,
                "--margin", "0.2sec",
                "--edit", f"audio:threshold={silence_threshold}%",
                "-o", out_silence
            ]
            subprocess.run(cmd, check=True)
            current_video = out_silence
            log.append("✔ [ON] Silence Cut complete.")
        else:
            log.append("⏭ [OFF] Silence Cut skipped.")

        # STEP 2: 9:16 Vertical Crop (ON/OFF)
        if enable_vertical_crop:
            out_crop = "step2_vertical.mp4"
            cmd = [
                "ffmpeg", "-y", "-i", current_video,
                "-vf", "crop=ih*(9/16):ih",
                "-c:a", "copy", out_crop
            ]
            subprocess.run(cmd, check=True)
            current_video = out_crop
            log.append("✔ [ON] 9:16 Vertical Crop complete.")
        else:
            log.append("⏭ [OFF] 9:16 Vertical Crop skipped.")

        # Whisper Transcription (Sirf tab chalega jab Hook Auto-Detect ya Captions ON hon)
        segments = None
        if (enable_hook and hook_mode == "Auto-Detect from Speech") or enable_captions:
            log.append("🎙 Audio transcribe ho raha hai...")
            segments = transcribe_video(current_video)

        # STEP 3: Auto Hook Generator - First 3.5 Seconds (ON/OFF)
        if enable_hook:
            out_hook = "step3_hook.mp4"
            if hook_mode == "Custom Text" and custom_hook_text.strip():
                raw_hook = custom_hook_text.strip()
            elif segments and len(segments) > 0:
                # Pehle 1-2 segments se catchy hook text banana
                raw_hook = " ".join([s.text.strip() for s in segments[:2]])[:55].upper() + "..."
            else:
                raw_hook = "WATCH TILL THE END!"

            wrapped_hook = "\n".join(textwrap.wrap(raw_hook, width=22))
            safe_hook = escape_ffmpeg_text(wrapped_hook)

            vf_filters = []
            # Hook Zoom-In Effect (First 3.5 seconds mein smooth punch-in)
            if enable_hook_zoom:
                vf_filters.append(
                    "scale=iw*1.12:ih*1.12,crop=iw/1.12:ih/1.12:"
                    "x='if(lt(t,3.5), (iw-ow)/2, (iw-ow)/2)':"
                    "y='if(lt(t,3.5), (ih-oh)/2, (ih-oh)/2)'"
                )

            # Hook Banner Text Overlay (First 3.5 seconds)
            drawtext_filter = (
                f"drawtext=text='{safe_hook}':"
                "fontcolor=yellow:fontsize=42:borderw=3:bordercolor=black:"
                "box=1:boxcolor=black@0.65:boxborderw=14:"
                "x=(w-text_w)/2:y=h*0.18:"
                "enable='between(t,0,3.5)'"
            )
            vf_filters.append(drawtext_filter)
            vf_chain = ",".join(vf_filters)

            # Hook Sound Effect (Whoosh/Pop) agar ON aur file uploaded ho
            if enable_hook_sfx and hook_sfx_file:
                cmd = [
                    "ffmpeg", "-y", "-i", current_video, "-i", hook_sfx_file,
                    "-filter_complex",
                    f"[0:v]{vf_chain}[vout];[1:a]volume=0.8[sfx];[0:a][sfx]amix=inputs=2:duration=first[aout]",
                    "-map", "[vout]", "-map", "[aout]",
                    out_hook
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-i", current_video,
                    "-vf", vf_chain,
                    "-c:a", "copy", out_hook
                ]

            subprocess.run(cmd, check=True)
            current_video = out_hook
            log.append(f"✔ [ON] Auto Hook applied: '{raw_hook}'")
        else:
            log.append("⏭ [OFF] Auto Hook skipped.")

        # STEP 4: Auto Captions (ON/OFF)
        if enable_captions and segments:
            srt_file = "captions.srt"
            out_subs = "step4_captions.mp4"
            generate_srt(segments, srt_file)
            style = f"FontSize={caption_font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,MarginV=45"
            cmd = [
                "ffmpeg", "-y", "-i", current_video,
                "-vf", f"subtitles={srt_file}:force_style='{style}'",
                "-c:a", "copy", out_subs
            ]
            subprocess.run(cmd, check=True)
            current_video = out_subs
            log.append("✔ [ON] Auto Captions burn complete.")
        else:
            log.append("⏭ [OFF] Auto Captions skipped.")

        # STEP 5: Background Music (ON/OFF)
        if enable_bgm and bgm_file:
            out_bgm = "final_output.mp4"
            cmd = [
                "ffmpeg", "-y", "-i", current_video, "-i", bgm_file,
                "-filter_complex",
                f"[1:a]volume={bgm_volume}[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", out_bgm
            ]
            subprocess.run(cmd, check=True)
            current_video = out_bgm
            log.append("✔ [ON] Background Music merged.")
        else:
            log.append("⏭ [OFF] Background Music skipped.")

        log.append("\n🎉 Final Video Ready!")
        return current_video, "\n".join(log)

    except Exception as e:
        return None, f"❌ Error aaya hai:\n{str(e)}"


# ==================== GRADIO UI DASHBOARD ====================
with gr.Blocks(theme=gr.themes.Soft(), title="Free Video Edit Automation Studio") as demo:
    gr.Markdown("# 🎬 Free Video Edit Automation Studio (Modular ON/OFF Controls)")
    
    with gr.Row():
        # Left Column: Input & Feature Toggles
        with gr.Column(scale=1):
            video_in = gr.Video(label="1. Apna Raw Video Upload Karein")
            
            with gr.Accordion("🪝 1. Auto Hook Settings (First 3.5 Sec)", open=True):
                chk_hook = gr.Checkbox(label="Enable Auto Hook (ON / OFF)", value=True)
                hook_mode = gr.Radio(
                    ["Auto-Detect from Speech", "Custom Text"],
                    value="Auto-Detect from Speech",
                    label="Hook Text Source"
                )
                custom_hook_text = gr.Textbox(
                    label="Custom Hook Text",
                    placeholder="E.g., 99% log yeh galti karte hain..."
                )
                chk_hook_zoom = gr.Checkbox(label="Hook Punch Zoom-In (ON / OFF)", value=True)
                chk_hook_sfx = gr.Checkbox(label="Hook Sound Effect - Whoosh/Pop (ON / OFF)", value=False)
                hook_sfx_file = gr.Audio(type="filepath", label="Hook SFX Audio File (Optional)")

            with gr.Accordion("✂️ 2. Silence Removal (Jump Cuts)", open=True):
                chk_silence = gr.Checkbox(label="Enable Silence Cut (ON / OFF)", value=True)
                sld_silence = gr.Slider(1, 15, value=4, step=1, label="Silence Sensitivity (%)")

            with gr.Accordion("📱 3. Format & Aspect Ratio", open=False):
                chk_crop = gr.Checkbox(label="Convert to 9:16 Vertical (Reels/Shorts) (ON / OFF)", value=False)

            with gr.Accordion("💬 4. Auto Captions (Subtitles)", open=True):
                chk_subs = gr.Checkbox(label="Enable Auto Captions (ON / OFF)", value=True)
                sld_font = gr.Slider(12, 36, value=20, step=2, label="Caption Font Size")

            with gr.Accordion("🎵 5. Background Music", open=False):
                chk_bgm = gr.Checkbox(label="Enable Background Music (ON / OFF)", value=False)
                audio_in = gr.Audio(type="filepath", label="Upload Background Music (MP3/WAV)")
                sld_vol = gr.Slider(0.05, 0.5, value=0.15, step=0.05, label="Music Volume")

            run_btn = gr.Button("🚀 Start Auto Edit", variant="primary", size="lg")

        # Right Column: Output Preview & Logs
        with gr.Column(scale=1):
            video_out = gr.Video(label="Final Edited Video")
            status_box = gr.Textbox(label="Live Processing Logs", lines=12)

    run_btn.click(
        fn=process_video,
        inputs=[
            video_in,
            chk_silence, sld_silence,
            chk_crop,
            chk_hook, hook_mode, custom_hook_text, chk_hook_zoom, chk_hook_sfx, hook_sfx_file,
            chk_subs, sld_font,
            chk_bgm, audio_in, sld_vol
        ],
        outputs=[video_out, status_box]
    )

if __name__ == "__main__":
    demo.launch(share=True)
