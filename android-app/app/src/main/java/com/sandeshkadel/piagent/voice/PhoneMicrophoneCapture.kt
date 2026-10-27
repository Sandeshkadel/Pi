package com.sandeshkadel.piagent.voice

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import com.sandeshkadel.piagent.connection.AudioInputMessageEncoder
import java.util.concurrent.atomic.AtomicBoolean

enum class CaptureEndReason {
    USER_STOPPED,
    DURATION_LIMIT,
}

class PhoneMicrophoneCapture(private val context: Context) {
    private var activeSession: Session? = null

    val isRecording: Boolean
        @Synchronized get() = activeSession?.recording?.get() == true

    @Synchronized
    fun start(
        onAudioFrame: (ByteArray) -> Boolean,
        onCaptureEnded: (CaptureEndReason) -> Unit,
        onFailure: (String) -> Unit,
    ) {
        check(activeSession == null) { "Stop the current microphone capture first." }
        check(
            context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED,
        ) {
            "Allow microphone access before starting voice capture."
        }

        val minimumBufferBytes = AudioRecord.getMinBufferSize(
            AUDIO_INPUT_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        check(minimumBufferBytes > 0) { "The phone does not support 16 kHz mono audio capture." }
        val recorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            AUDIO_INPUT_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minimumBufferBytes, AUDIO_INPUT_FRAME_BYTES * 4),
        )
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            throw IllegalStateException("The phone microphone could not be initialized.")
        }

        try {
            recorder.startRecording()
        } catch (error: IllegalStateException) {
            recorder.release()
            throw IllegalStateException("The phone microphone could not start recording.", error)
        } catch (error: SecurityException) {
            recorder.release()
            throw SecurityException("Allow microphone access before starting voice capture.", error)
        }

        val session = Session(recorder, onAudioFrame, onCaptureEnded, onFailure)
        activeSession = session
        Thread({ capture(session) }, "piagent-phone-microphone").apply {
            isDaemon = true
            start()
        }
    }

    @Synchronized
    fun stop(finalizeSession: Boolean = true) {
        val session = activeSession ?: return
        activeSession = null
        session.endReason = if (finalizeSession) CaptureEndReason.USER_STOPPED else null
        session.recording.set(false)
        stopRecorder(session.recorder)
    }

    private fun capture(session: Session) {
        val frame = ByteArray(AUDIO_INPUT_FRAME_BYTES)
        val startedAt = SystemClock.elapsedRealtime()
        try {
            while (session.recording.get()) {
                if (SystemClock.elapsedRealtime() - startedAt >= MAX_CAPTURE_MILLIS) {
                    session.endReason = CaptureEndReason.DURATION_LIMIT
                    session.recording.set(false)
                    break
                }
                val count = session.recorder.read(frame, 0, frame.size, AudioRecord.READ_BLOCKING)
                if (!session.recording.get()) break
                if (count < 0) {
                    throw IllegalStateException("Phone microphone read failed (error $count).")
                }
                if (count == 0) continue
                if (count % 2 != 0) {
                    throw IllegalStateException("Phone microphone returned an incomplete PCM sample.")
                }
                if (!session.onAudioFrame(frame.copyOf(count))) {
                    throw IllegalStateException("The Pi connection could not accept microphone audio.")
                }
            }
        } catch (error: IllegalStateException) {
            fail(session, error.message ?: "Phone microphone capture stopped unexpectedly.")
        } catch (error: SecurityException) {
            fail(session, "Phone microphone permission was revoked during capture.")
        } finally {
            session.recorder.release()
            synchronized(this) {
                if (activeSession === session) activeSession = null
            }
            session.endReason?.let(session.onCaptureEnded)
        }
    }

    private fun fail(session: Session, message: String) {
        session.recording.set(false)
        session.endReason = null
        session.onFailure(message)
    }

    private fun stopRecorder(recorder: AudioRecord) {
        try {
            if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                recorder.stop()
            }
        } catch (_: IllegalStateException) {
            // A concurrent read failure can stop the recorder before the UI does.
        }
    }

    private class Session(
        val recorder: AudioRecord,
        val onAudioFrame: (ByteArray) -> Boolean,
        val onCaptureEnded: (CaptureEndReason) -> Unit,
        val onFailure: (String) -> Unit,
        val recording: AtomicBoolean = AtomicBoolean(true),
        @Volatile var endReason: CaptureEndReason? = null,
    )

    private companion object {
        const val AUDIO_INPUT_SAMPLE_RATE = AudioInputMessageEncoder.SAMPLE_RATE
        const val AUDIO_INPUT_FRAME_BYTES = AudioInputMessageEncoder.FRAME_BYTES
        const val MAX_CAPTURE_MILLIS = 30_000L
    }
}
