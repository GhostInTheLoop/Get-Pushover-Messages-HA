# Get-Pushover-Messages-HA
This Home Assistant integration uses the Pushover Open Client API to download the latest message from Pushover and put it in a sensor so you can use it for automations.

I use it to announce the pushover notifications over Alexa.

You MUST use MFA on your pushover account.

What does this integration do?

The plugin will Register a device in your pushover account called 'home_assiatant'
The integration will download the latest message every 10 seconds.
Once it has downloaded the message it writes it to a sensor so it can be used - NOTE this sensor will show 'No messages' if there are no new messages after 10 seconds, it does not save the last message.