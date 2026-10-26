package com.sandeshkadel.piagent

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.sandeshkadel.piagent.connection.AgentConnectionClient
import com.sandeshkadel.piagent.connection.ConnectionEndpoint
import com.sandeshkadel.piagent.connection.ConnectionState

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    PiAgentHome(
                        onCreateConnection = { onState ->
                            AgentConnectionClient { nextState ->
                                runOnUiThread { onState(nextState) }
                            }
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun PiAgentHome(
    onCreateConnection: ((ConnectionState) -> Unit) -> AgentConnectionClient,
) {
    var endpoint by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var connectionState by remember {
        mutableStateOf(ConnectionState.Disconnected)
    }
    var validationMessage by remember { mutableStateOf<String?>(null) }
    val endpointFocusRequester = remember { FocusRequester() }
    val tokenFocusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current
    val client = remember { onCreateConnection { connectionState = it } }

    DisposableEffect(client) {
        onDispose { client.close() }
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
                    visualTransformation = PasswordVisualTransformation(),
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
                            token = ""
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
                status = "Not requested",
                detail = "Will be requested when voice capture is implemented and you enable it.",
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
                "Connection currently supports authentication and heartbeat checks. " +
                    "Voice, BLE pairing, notifications, and phone actions are not enabled yet.",
                modifier = Modifier.padding(16.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
            )
        }
        Spacer(Modifier.height(4.dp))
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
