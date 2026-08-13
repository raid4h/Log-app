# legal_content.py
#
# The actual text shown on screens/terms_screen.py (agreement gate,
# shown on first launch and again if TERMS_VERSION is ever bumped)
# and screens/privacy_policy_screen.py (read-only, reachable from
# Settings > About).
#
# DRAFT CONTENT: written to be structurally reasonable for a fully
# offline, no-data-collection app, but this is NOT legal advice --
# meant to be reviewed (ideally by a professional) before shipping,
# same as you'd review any other legal document before it goes in
# front of real users.
#
# Bump TERMS_VERSION any time the TERMS_TEXT below actually changes
# in a way that matters -- services/legal_store.py compares this
# number against what the user last agreed to, and will show the
# terms screen again if they don't match, rather than silently
# assuming an old agreement covers new terms the user never saw.
#
# v2: app renamed from "NoteNest" to "Log", developer credit updated
# to "NoteNestDev" -- a real change to what the user is agreeing to,
# so the version bumped rather than editing v1 in place.

TERMS_VERSION = 2

APP_NAME = "Log"

DEVELOPER_NAME = "NoteNestDev"

TERMS_TEXT = f"""Terms & Conditions

Last updated: [DATE -- fill in before release]

Please read these Terms & Conditions carefully before using {APP_NAME}. By tapping "I Agree," you confirm that you have read, understood, and agree to be bound by these terms.

1. Acceptance of Terms

By installing, accessing, or using {APP_NAME}, you agree to these Terms & Conditions and to the {APP_NAME} Privacy Policy. If you do not agree, please do not use the app.

2. What {APP_NAME} Is

{APP_NAME} is a note-taking and personal organization app, developed by {DEVELOPER_NAME}, that runs entirely on your device. It does not require an account, does not connect to the internet to function, and does not transmit your data anywhere.

3. Your Data and Content

All notes, tasks, checklists, reminders, and other content you create in {APP_NAME} ("Your Content") are stored locally on your device only. You retain full ownership of Your Content at all times. {APP_NAME} does not access, view, collect, or transmit Your Content to us or to any third party, because {APP_NAME} has no servers and no network connection to send it through.

4. Your Responsibility for Backups

{APP_NAME} provides a manual export/import feature so you can back up Your Content to a file of your choosing. Because all data lives only on your device:
- If you uninstall {APP_NAME}, lose your device, or your device's storage is damaged, Your Content may be permanently lost unless you have exported a backup beforehand.
- We are not able to recover Your Content for you under any circumstances, since we never have a copy of it.
- You are solely responsible for creating and safely storing your own backups.

5. Permissions

{APP_NAME} may request the following device permissions, used only for the stated purpose and never for tracking or data collection:
- Notifications -- to alert you about tasks and reminders you set.
- Photos / Storage (fallback only) -- to let you attach an image to a note, on devices where Android's built-in Photo Picker isn't available.
You can review and manage these at any time from Settings > Privacy, or through your device's own system settings.

6. Acceptable Use

You agree not to use {APP_NAME} for any unlawful purpose, and not to attempt to reverse-engineer, decompile, or tamper with the app in a way that violates applicable law.

7. No Warranty

{APP_NAME} is provided "as is," without warranty of any kind, express or implied. We do not guarantee the app will be error-free, uninterrupted, or fit for any particular purpose.

8. Limitation of Liability

To the fullest extent permitted by law, {DEVELOPER_NAME} shall not be liable for any indirect, incidental, or consequential damages, including loss of data, arising from your use of {APP_NAME}.

9. Changes to These Terms

We may update these Terms & Conditions from time to time. If we make a material change, you will be asked to review and agree to the updated terms the next time you open the app.

10. Contact

Questions about these terms can be directed to: [CONTACT EMAIL -- fill in before release]

By tapping "I Agree" below, you confirm you have read and accepted these Terms & Conditions and the {APP_NAME} Privacy Policy.
"""

PRIVACY_POLICY_TEXT = f"""Privacy Policy

Last updated: [DATE -- fill in before release]

This Privacy Policy explains how {APP_NAME}, developed by {DEVELOPER_NAME}, handles information. The short version: {APP_NAME} does not collect, store, or transmit any of your personal data anywhere, because it doesn't have to -- everything happens entirely on your own device.

1. No Data Collection

{APP_NAME} does not have a server, does not require an account, does not use analytics or tracking tools, and does not collect any personal information about you. We do not know who you are, what you write in your notes, or how you use the app, because none of that information ever leaves your device.

2. Where Your Data Lives

All notes, tasks, checklists, reminders, categories, and attached images you create are stored locally in {APP_NAME}'s own private storage on your device. This data is never uploaded, synced, or shared with us or with any third party.

3. Backups You Create

{APP_NAME} includes a manual export feature that lets you save a backup of your data as a file, to a location you choose on your own device. This file is created and controlled entirely by you -- {APP_NAME} does not access it, upload it, or send it anywhere once it's created. If you choose to share that file (for example, by emailing it to yourself or uploading it to your own cloud storage), that is entirely your own action and outside {APP_NAME}'s control.

4. Permissions We Request, and Why

| Permission | Purpose |
|---|---|
| Notifications | To show you an alert when a task or reminder you created is due. |
| Photos (fallback) | Only used on devices without Android's built-in Photo Picker, so you can still attach an image to a note. |
| Storage (legacy fallback) | Same purpose as Photos, for older Android versions. |

None of these permissions are used to collect, monitor, or transmit data about you. You can review the current status of each permission at any time from Settings > Privacy within the app, and grant or revoke them through your device's own system settings.

5. Children's Privacy

{APP_NAME} does not knowingly collect any information from anyone, including children, because it does not collect information from anyone at all.

6. Third Parties

{APP_NAME} does not integrate with, or share data with, any third-party service, advertising network, or analytics provider.

7. Changes to This Policy

If this Privacy Policy is ever updated, the "Last updated" date above will change, and material changes will be reflected in the app.

8. Contact

Questions about this policy can be directed to: [CONTACT EMAIL -- fill in before release]
"""