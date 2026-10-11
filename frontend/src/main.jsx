// Starting point of the app: loads fonts and Mantine styles, then shows the
// page that matches the address (see router.jsx).

import '@fontsource/public-sans/400.css';
import '@fontsource/public-sans/500.css';
import '@fontsource/public-sans/600.css';
import '@fontsource/public-sans/700.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource/ibm-plex-mono/600.css';
import '@mantine/core/styles.css';
import '@mantine/dropzone/styles.css';
import './styles/global.css';

import { MantineProvider } from '@mantine/core';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router/dom';

import { router } from './router';
import { cssVariablesResolver, theme } from './theme';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MantineProvider
      theme={theme}
      cssVariablesResolver={cssVariablesResolver}
      defaultColorScheme="light"
    >
      <RouterProvider router={router} />
    </MantineProvider>
  </StrictMode>,
);
