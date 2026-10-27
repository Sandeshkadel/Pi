package com.sandeshkadel.piagent

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.sandeshkadel.piagent.connection.AgentConnectionClient
import com.sandeshkadel.piagent.connection.ConnectionEndpoint
import com.sandeshkadel.piagent.connection.ConnectionState
import com.sandeshkadel.piagent.connection.SpeakMessage
import com.sandeshkadel.piagent.voice.AgentSpeechPlayer
import com.sandeshkadel.piagent.voice.CaptureEndReason
import com.sandeshkadel.piagent.voice.PhoneMicrophoneCapture
import com.sandeshkadel.piagent.voice.SpeechTuning
import com.sandeshkadel.piagent.voice.SpeechOutputState
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    var speechState by remember {
                        mutableStateOf(SpeechOutputState.Initializing)
                    }
                    val speechPlayer = remember {
                        AgentSpeechPlayer(applicationContext) { nextState ->
                            runOnUiThread { speechState = nextState }
                        }
                    }
                    PiAgentHome(
                        speechState = speechState,
                        speechPlayer = speechPlayer,
                        onCreateConnection = { onState, onSpeech, onListening, onProtocolError ->
                            AgentConnectionClient(
                                onStateChanged = onState,
                                onSpeechReceived = onSpeech,
                                onListening = onListening,
                                onProtocolError = onProtocolError,
                            )
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun PiAgentHome(
    speechState: SpeechOutputState,
    speechPlayer: AgentSpeechPlayer,
    onCreateConnection: (
        (ConnectionState) -> Unit,
        (SpeakMessage) -> Unit,
        () -> Unit,
        (String, String) -> Unit,
    ) -> AgentConnectionClient,
) {
    var endpoint by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var tokenVisible by remember { mutableStateOf(false) }
    var connectionState by remember {
        mutableStateOf(ConnectionState.Disconnected)
    }
    var validationMessage by remember { mutableStateOf<String?>(null) }
    val endpointFocusRequester = remember { FocusRequester() }
    val tokenFocusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val mainHandler = remember { Handler(Looper.getMainLooper()) }
    val microphoneCapture = remember(context) { PhoneMicrophoneCapture(context) }
    var microphoneRecording by remember { mutableStateOf(false) }
    var microphoneStatus by remember {
        mutableStateOf("Connect to your Pi before starting microphone capture.")
    }
    val voicePreferences = remember(context) {
        context.getSharedPreferences(VOICE_PREFERENCES, Context.MODE_PRIVATE)
    }
    var tuning by remember(voicePreferences) {
        mutableStateOf(
            SpeechTuning(
                pitch = voicePreferences.getFloat(
                    PITCH_PREFERENCE,
                    SpeechTuning.DEFAULT_PITCH,
                ).coerceIn(SpeechTuning.MIN_VALUE, SpeechTuning.MAX_VALUE),
                rate = voicePreferences.getFloat(
                    RATE_PREFERENCE,
                    SpeechTuning.DEFAULT_RATE,
                ).coerceIn(SpeechTuning.MIN_VALUE, SpeechTuning.MAX_VALUE),
            ),
        )
    }
    var speakConnectionCue by remember(voicePreferences) {
        mutableStateOf(voicePreferences.getBoolean(CONNECTION_CUE_PREFERENCE, true))
    }
    val client = remember {
        onCreateConnection(
            { nextState ->
                mainHandler.post {
                    connectionState = nextState
                    if (!nextState.isConnected && !nextState.isConnecting) {
                        speechPlayer.stop()
                        val wasRecording = microphoneCapture.isRecording
                        microphoneCapture.stop(sendEndOfAudio = false)
                        microphoneRecording = false
                        if (wasRecording) {
                            microphoneStatus =
                                "Microphone stopped because the Pi disconnected."
                        }
                    }
                }
            },
            { message -> speechPlayer.speak(message.text, message.interrupt) },
            {
                mainHandler.post {
                    microphoneStatus = "Pi heard “Hey Pi”. Say your command, then tap Stop."
                }
            },
            { _, detail ->
                mainHandler.post {
                    microphoneCapture.stop(sendEndOfAudio = false)
                    microphoneRecording = false
                    microphoneStatus = detail
                }
            },
        )
    }

    DisposableEffect(client) {
        onDispose { client.close() }
    }
    DisposableEffect(speechPlayer) {
        onDispose { speechPlayer.close() }
    }
    DisposableEffect(lifecycleOwner, microphoneCapture) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                val wasRecording = microphoneCapture.isRecording
                microphoneCapture.stop(sendEndOfAudio = false)
                microphoneRecording = false
                if (wasRecording) {
                    microphoneStatus = "Microphone stopped when PiAgent left the screen."
                }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            microphoneCapture.stop(sendEndOfAudio = false)
        }
    }
    LaunchedEffect(tuning) {
        speechPlayer.setTuning(tuning)
        voicePreferences.edit()
            .putFloat(PITCH_PREFERENCE, tuning.pitch)
            .putFloat(RATE_PREFERENCE, tuning.rate)
            .apply()
    }
    LaunchedEffect(speakConnectionCue) {
        voicePreferences.edit()
            .putBoolean(CONNECTION_CUE_PREFERENCE, speakConnectionCue)
            .apply()
    }
    LaunchedEffect(connectionState.isConnected, speakConnectionCue) {
        if (connectionState.isConnected && speakConnectionCue) {
            speechPlayer.speak("Pi is connected and ready.", interrupt = false)
        }
    }
    val startMicrophone: () -> Unit = {
        if (!connectionState.isConnected) {
            microphoneStatus = "Connect to your Pi before starting microphone capture."
        } else {
            try {
                microphoneCapture.start(
                    onAudioFrame = client::sendAudioFrame,
                    onCaptureEnded = { reason ->
                        val sent = client.sendEndOfAudio()
                        mainHandler.post {
                            microphoneRecording = false
                            microphoneStatus = if (!sent) {
                                "The Pi connection ended before audio could be finalized."
                            } else if (reason == CaptureEndReason.DURATION_LIMIT) {
                                "The 30-second microphone limit was reached; waiting for Pi."
                            } else {
                                "Audio sent. Waiting for the Pi voice processor."
                            }
                        }
                    },
                    onFailure = { detail ->
                        mainHandler.post {
                            microphoneRecording = false
                            microphoneStatus = detail
                        }
                    },
                )
                microphoneRecording = true
                microphoneStatus =
                    "Microphone is on. Say “Hey Pi” and your command, then tap Stop."
            } catch (error: IllegalStateException) {
                microphoneStatus = error.message ?: "Phone microphone capture could not start."
            } catch (error: SecurityException) {
                microphoneStatus = error.message ?: "Allow microphone access to use voice input."
            }
        }
    }
    val microphonePermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            startMicrophone()
        } else {
            microphoneStatus = "Microphone permission was denied. Voice input is off."
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 28.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("PiAgent", style = MaterialTheme.typography.headlineLarge)
            Text(
                "Connect to your Pi over your local network.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        ConnectionStatusCard(connectionState)

        MicrophoneCaptureCard(
            connected = connectionState.isConnected,
            recording = microphoneRecording,
            status = microphoneStatus,
            onToggle = {
                if (microphoneRecording) {
                    microphoneCapture.stop()
                    microphoneRecording = false
                    microphoneStatus = "Finishing audio and sending it to the Pi."
                } else if (
                    context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                    PackageManager.PERMISSION_GRANTED
                ) {
                    startMicrophone()
                } else {
                    microphonePermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                }
            },
        )

        Card {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text("Connect to your Pi", style = MaterialTheme.typography.titleLarge)
                Text(
                    "Enter the local WebSocket address and the agent token configured on your Pi.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    "Use wss:// for encrypted transport. ws:// sends the token unencrypted; " +
                        "use it only on a trusted, isolated network.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
                OutlinedTextField(
                    value = endpoint,
                    onValueChange = {
                        endpoint = it
                        validationMessage = null
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(endpointFocusRequester),
                    label = { Text("Pi WebSocket address") },
                    placeholder = { Text("ws://192.168.0.10:8000/ws/agent") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Uri,
                        imeAction = ImeAction.Next,
                    ),
                    keyboardActions = KeyboardActions(
                        onNext = { tokenFocusRequester.requestFocus() },
                    ),
                    enabled = !connectionState.isConnecting && !connectionState.isConnected,
                )
                OutlinedTextField(
                    value = token,
                    onValueChange = {
                        token = it
                        validationMessage = null
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(tokenFocusRequester),
                    label = { Text("Agent token") },
                    singleLine = true,
                    visualTransformation = if (tokenVisible) {
                        VisualTransformation.None
                    } else {
                        PasswordVisualTransformation()
                    },
                    trailingIcon = {
                        IconButton(
                            onClick = { tokenVisible = !tokenVisible },
                            enabled = !connectionState.isConnecting && !connectionState.isConnected,
                        ) {
                            Icon(
                                painter = androidx.compose.ui.res.painterResource(
                                    if (tokenVisible) {
                                        R.drawable.ic_visibility_off
                                    } else {
                                        R.drawable.ic_visibility
                                    },
                                ),
                                contentDescription = if (tokenVisible) {
                                    "Hide agent token"
                                } else {
                                    "Show agent token"
                                },
                            )
                        }
                    },
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Password,
                        imeAction = ImeAction.Done,
                    ),
                    keyboardActions = KeyboardActions(
                        onDone = { keyboardController?.hide() },
                    ),
                    enabled = !connectionState.isConnecting && !connectionState.isConnected,
                    supportingText = {
                        Text("Used for authentication only; it is not saved on this device.")
                    },
                )

                validationMessage?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }

                if (connectionState.isConnected) {
                    TextButton(
                        onClick = {
                            client.disconnect()
                            speechPlayer.stop()
                            token = ""
                            tokenVisible = false
                            connectionState = ConnectionState.Disconnected
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("Disconnect")
                    }
                } else {
                    Button(
                        onClick = {
                            try {
                                keyboardController?.hide()
                                ConnectionEndpoint.validate(endpoint)
                                ConnectionEndpoint.validateToken(token)
                                validationMessage = null
                                client.connect(endpoint.trim(), token)
                            } catch (error: IllegalArgumentException) {
                                validationMessage = error.message
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !connectionState.isConnecting,
                    ) {
                        Text(if (connectionState.isConnecting) "Connecting…" else "Connect")
                    }
                }
            }
        }

        SpeechOutputCard(
            state = speechState,
            tuning = tuning,
            onTuningChanged = { tuning = it },
            speakConnectionCue = speakConnectionCue,
            onConnectionCueChanged = { speakConnectionCue = it },
            onPreview = {
                speechPlayer.speak("Hello, Pi is ready to help.", interrupt = true)
            },
        )

        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Permissions", style = MaterialTheme.typography.titleLarge)
            Text(
                "Only request a permission when you turn on the feature that needs it. " +
                    "The connection itself needs no sensitive runtime permission.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            PermissionStatusRow(
                title = "Bluetooth",
                status = "Not requested",
                detail = "Only needed for Pi discovery and provisioning; that flow is not ready yet.",
            )
            PermissionStatusRow(
                title = "Microphone",
                status = when {
                    microphoneRecording -> "In use"
                    context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                        PackageManager.PERMISSION_GRANTED -> "Allowed"
                    else -> "Ask on use"
                },
                detail = "Used only while you start voice capture; capture stops when the app " +
                    "leaves the screen. Speech replies use the phone speaker.",
            )
            PermissionStatusRow(
                title = "Notifications",
                status = "Not requested",
                detail = "Optional; request only when notification forwarding is available.",
            )
            PermissionStatusRow(
                title = "Accessibility",
                status = "Not requested",
                detail = "Optional automation is not implemented; it will never be enabled silently.",
            )
        }

        Card(
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.secondaryContainer,
            ),
        ) {
            Text(
                "Voice input streams 16 kHz microphone audio to the Pi while capture is active. " +
                    "The standard Pi server still needs local wake-word, VAD, and speech-recognition " +
                    "adapters configured. BLE, notifications, and phone actions are not enabled.",
                modifier = Modifier.padding(16.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
            )
        }
        Spacer(Modifier.height(4.dp))
    }
}

@Composable
private fun MicrophoneCaptureCard(
    connected: Boolean,
    recording: Boolean,
    status: String,
    onToggle: () -> Unit,
) {
    Card {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Phone microphone", style = MaterialTheme.typography.titleMedium)
            Text(
                "Tap Start, say “Hey Pi” and your command, then tap Stop. Audio streams to the " +
                    "authenticated Pi over WebSocket and is not saved by the app.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                status,
                style = MaterialTheme.typography.bodySmall,
                color = if (recording) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
            )
            Button(
                onClick = onToggle,
                enabled = connected,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (recording) "Stop microphone" else "Start microphone")
            }
        }
    }
}

@Composable
private fun SpeechOutputCard(
    state: SpeechOutputState,
    tuning: SpeechTuning,
    onTuningChanged: (SpeechTuning) -> Unit,
    speakConnectionCue: Boolean,
    onConnectionCueChanged: (Boolean) -> Unit,
    onPreview: () -> Unit,
) {
    Card {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Offline voice", style = MaterialTheme.typography.titleMedium)
            state.voiceName?.let {
                Text("Voice: $it", style = MaterialTheme.typography.bodyMedium)
            }
            Text(
                state.detail,
                style = MaterialTheme.typography.bodyMedium,
                color = if (state.ready) {
                    MaterialTheme.colorScheme.onSurfaceVariant
                } else {
                    MaterialTheme.colorScheme.error
                },
            )
            Text(
                "Adjust pitch and pace for the installed phone voice. " +
                    "Android does not provide a direct frequency-in-hertz control.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                "Pitch: ${String.format(Locale.ROOT, "%.2f", tuning.pitch)}×",
                style = MaterialTheme.typography.labelLarge,
            )
            Slider(
                value = tuning.pitch,
                onValueChange = { onTuningChanged(tuning.copy(pitch = it)) },
                valueRange = SpeechTuning.MIN_VALUE..SpeechTuning.MAX_VALUE,
                steps = 7,
            )
            Text(
                "Speaking rate: ${String.format(Locale.ROOT, "%.2f", tuning.rate)}×",
                style = MaterialTheme.typography.labelLarge,
            )
            Slider(
                value = tuning.rate,
                onValueChange = { onTuningChanged(tuning.copy(rate = it)) },
                valueRange = SpeechTuning.MIN_VALUE..SpeechTuning.MAX_VALUE,
                steps = 7,
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .toggleable(
                        value = speakConnectionCue,
                        role = Role.Switch,
                        onValueChange = onConnectionCueChanged,
                    ),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    "Speak a ready cue when connected",
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.bodyMedium,
                )
                Switch(
                    checked = speakConnectionCue,
                    onCheckedChange = null,
                )
            }
            TextButton(
                onClick = onPreview,
                enabled = state.ready,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Preview voice")
            }
        }
    }
}

@Composable
private fun ConnectionStatusCard(state: ConnectionState) {
    Card {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text("Pi connection", style = MaterialTheme.typography.titleMedium)
                Text(
                    state.detail,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                state.label,
                modifier = Modifier.padding(start = 12.dp),
                style = MaterialTheme.typography.labelLarge,
                color = if (state.isConnected) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
            )
        }
    }
}

@Composable
private fun PermissionStatusRow(title: String, status: String, detail: String) {
    Card {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                Text(
                    status,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Text(
                detail,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private const val VOICE_PREFERENCES = "piagent_voice_preferences"
private const val PITCH_PREFERENCE = "speech_pitch"
private const val RATE_PREFERENCE = "speech_rate"
private const val CONNECTION_CUE_PREFERENCE = "speak_connection_cue"
