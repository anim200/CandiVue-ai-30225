// Short pop-up messages in the top-right corner (design: "use
// @mantine/notifications for completion events"). One place, so every
// screen uses the same colours and wording style.

import { notifications } from '@mantine/notifications';

// Something finished, e.g. "Weights saved".
export function notifyDone(message) {
  notifications.show({ message, color: '#2D7A4E' });
}

// An action failed: what happened (title) and the plain-language reason.
export function notifyError(title, error) {
  notifications.show({ title, message: error.message, color: '#B03A2E', autoClose: 8000 });
}
