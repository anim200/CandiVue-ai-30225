// Knowledge base (design: Knowledge Base.dc.html): documents the Hiring
// Assistant searches (RAG). Upload, see indexing status, remove, and test a
// search. Never upload CVs or personal data here (warning banner).
// Not built yet: document preview, and the "personal data" scan (a design
// proposal), so the banner does not claim files are scanned.

import { Button, Select, Text, TextInput } from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import { useDocumentTitle } from '@mantine/hooks';
import {
  IconAlertTriangle,
  IconBook2,
  IconBooks,
  IconBriefcase,
  IconBuilding,
  IconCheck,
  IconCloudUpload,
  IconDatabaseOff,
  IconFileDownload,
  IconFileX,
  IconMail,
  IconMessageQuestion,
  IconSearch,
  IconSearchOff,
  IconShieldLock,
  IconTrash,
} from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiDelete, apiGet, apiPost, apiPostAi, apiUpload } from '../../api/client';
import ConfirmModal from '../../components/ConfirmModal';
import { EmptyState, ErrorBanner } from '../../components/Feedback';
import { notifyDone, notifyError } from '../../components/notify';
import StatusBadge from '../../components/StatusBadge';
import { shortDate } from '../JobsPage';
import { COLLECTION_SHORT } from '../assistant/labels';
import classes from './KnowledgeBase.module.css';

const MAX_MB = 20;
const POLL_MS = 2000; // refresh while documents are being indexed

// Collections, their icons and what each is used for (from the design).
const COLLECTIONS = [
  { key: 'all', name: 'All documents', icon: IconBooks, use: 'Everything in the index' },
  { key: 'reference_library', name: 'Reference library', icon: IconBook2, use: 'Technical docs for writing JDs and checking answers' },
  { key: 'company_policies', name: 'Company policies', icon: IconBuilding, use: 'Used when writing job descriptions' },
  { key: 'previous_job_profiles', name: 'Previous job profiles', icon: IconBriefcase, use: 'Starting points for new jobs' },
  { key: 'email_templates', name: 'Email templates', icon: IconMail, use: 'Invitation and reminder wording' },
  { key: 'question_bank', name: 'Interview question bank', icon: IconMessageQuestion, use: 'Questions suggested during interviews' },
];
const NAME_OF = Object.fromEntries(COLLECTIONS.map((c) => [c.key, c.name]));

// File types the backend accepts (checked again there, by content).
const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'text/plain': ['.txt'],
  'text/markdown': ['.md', '.markdown'],
};

// File-type tile colours (design).
const TYPE_COLORS = {
  pdf: ['#FBE9E7', '#932E24'],
  docx: ['#E7EEF9', '#234E8B'],
  md: ['#EEF1F3', '#3E484F'],
  txt: ['#EEF1F3', '#3E484F'],
};

// "3.2 MB" / "84 KB" from a number of bytes.
function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// True while a document is waiting to be indexed or being indexed.
function isIndexing(doc) {
  return doc.status === 'pending' || doc.status === 'running' || doc.status === 'uploading';
}

// Status badge: Uploading / Indexing (with spinner and moving bar), Ready, Failed.
function DocStatus({ doc }) {
  if (isIndexing(doc)) {
    return (
      <div className={classes.statusCell}>
        <StatusBadge tone="info" icon={<span className={classes.badgeSpinner} />}>
          {doc.status === 'uploading' ? 'Uploading' : 'Indexing'}
        </StatusBadge>
        <div className={classes.bar}>
          <div className={classes.barFill} />
        </div>
      </div>
    );
  }
  if (doc.status === 'completed') {
    return (
      <StatusBadge tone="success" icon={<IconCheck size={13} />}>
        Ready
      </StatusBadge>
    );
  }
  return (
    <StatusBadge tone="danger" icon={<IconAlertTriangle size={13} />}>
      Failed
    </StatusBadge>
  );
}

// Left column: pick a collection to filter the table.
function CollectionNav({ active, counts, onPick }) {
  return (
    <nav className={classes.collections} aria-label="Collections">
      <div className={classes.collectionsTitle}>Collections</div>
      {COLLECTIONS.map(({ key, name, icon: Icon, use }) => (
        <button
          key={key}
          type="button"
          className={`${classes.collection} ${active === key ? classes.collectionActive : ''}`}
          onClick={() => onPick(key)}
        >
          <Icon size={18} className={classes.collectionIcon} />
          <span className={classes.collectionText}>
            <span className={classes.collectionName}>
              {name}
              <span className={classes.count}>{counts[key] ?? 0}</span>
            </span>
            <span className={classes.use}>{use}</span>
          </span>
        </button>
      ))}
    </nav>
  );
}

// One document row, plus a message row when indexing failed.
function DocumentRow({ doc, onRemove, onRetry }) {
  const [bg, fg] = TYPE_COLORS[doc.file_type] ?? TYPE_COLORS.txt;
  return (
    <div className={classes.docItem}>
      <div className={classes.row}>
        <div className={classes.docName}>
          <span className={classes.typeTile} style={{ background: bg, color: fg }}>
            {doc.file_type.toUpperCase()}
          </span>
          <span className={classes.nameText}>
            <b title={doc.filename}>{doc.filename}</b>
            <span className={classes.small}>
              {formatSize(doc.size_bytes)} · added {shortDate(doc.created_at)}
            </span>
          </span>
        </div>
        <div className={`${classes.collectionCell} ${classes.wide}`}>{NAME_OF[doc.collection]}</div>
        <DocStatus doc={doc} />
        <div className={`${classes.number} ${classes.wide}`}>{doc.chunk_count || '—'}</div>
        {doc.id > 0 ? (
          <button type="button" className={classes.iconButton} title="Remove" aria-label={`Remove ${doc.filename}`} onClick={() => onRemove(doc)}>
            <IconTrash size={16} />
          </button>
        ) : (
          <span />
        )}
      </div>
      {doc.status === 'failed' && (
        <div className={classes.message}>
          <span className={classes.messageText}>{doc.error ?? 'This file could not be added.'}</span>
          {doc.id > 0 && (
            <button type="button" className={classes.link} onClick={() => onRetry(doc)}>
              Try again
            </button>
          )}
          {doc.id > 0 && (
            <button type="button" className={classes.link} onClick={() => onRemove(doc)}>
              Remove file
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// "Try a search": shows which passages the assistant would find (RAG test).
function RetrievalTest({ collection }) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState(null); // null = no search yet
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);

  // Run the search on the backend.
  async function search(event) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setError(null);
    try {
      const body = { query: query.trim(), collection: collection === 'all' ? null : collection };
      setHits(await apiPostAi('/knowledge/search', body));
    } catch (err) {
      setError(err.message);
      setHits(null);
    } finally {
      setSearching(false);
    }
  }

  return (
    <form className={classes.search} onSubmit={search}>
      <div>
        <Text fz={17} fw={600}>
          Try a search
        </Text>
        <Text fz={14} c="dimmed" mt={2}>
          See which passages the assistant would find for a question.
        </Text>
      </div>
      <div className={classes.searchRow}>
        <TextInput
          style={{ flex: 1 }}
          leftSection={<IconSearch size={16} />}
          placeholder="e.g. interview questions about database migrations"
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          maxLength={500}
          aria-label="Search question"
        />
        <Button type="submit" variant="light" disabled={query.trim().length < 2 || searching}>
          Search
        </Button>
      </div>
      {searching && (
        <div className={classes.searching}>
          <span className={classes.spinner} />
          Searching…
        </div>
      )}
      {error && <ErrorBanner title="The search didn’t work.">{error}</ErrorBanner>}
      {hits?.length === 0 && (
        <div className={classes.noHits}>
          <IconSearchOff size={18} color="#66717A" />
          No passages matched closely enough. The assistant would answer without a reference for
          this question. Try different words, or upload a document that covers it.
        </div>
      )}
      {hits?.map((hit, index) => (
        <div key={index} className={classes.hit}>
          <div className={classes.hitTop}>
            <span className={classes.hitSource}>
              {COLLECTION_SHORT[hit.collection]} · {hit.filename}
            </span>
            <span className={classes.match}>
              match
              <span className={classes.matchTrack}>
                <span className={classes.matchFill} style={{ width: `${Math.round(hit.score * 100)}%`, display: 'block' }} />
              </span>
            </span>
          </div>
          <div className={classes.hitText}>{hit.text}</div>
        </div>
      ))}
    </form>
  );
}

// The knowledge base page.
export default function KnowledgeBasePage() {
  const [docs, setDocs] = useState(null); // null = loading
  const [failed, setFailed] = useState(false);
  const [uploads, setUploads] = useState([]); // files still uploading (shown at once)
  const [rejected, setRejected] = useState([]); // files refused before upload
  const [active, setActive] = useState('all');
  const [target, setTarget] = useState('reference_library');
  const [removing, setRemoving] = useState(null); // document waiting for confirmation
  const [removeBusy, setRemoveBusy] = useState(false);
  const openRef = useRef(null);
  useDocumentTitle('Knowledge base · CandiVue AI');

  // Load the document list.
  const load = useCallback(async () => {
    try {
      setDocs(await apiGet('/knowledge/documents'));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // While anything is being indexed, refresh every 2 seconds.
  useEffect(() => {
    if (!docs?.some(isIndexing)) return undefined;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [docs, load]);

  // Picking a collection also makes it the upload target.
  function pickCollection(key) {
    setActive(key);
    if (key !== 'all') setTarget(key);
  }

  // Upload the dropped files one after another; each appears at once as "Uploading".
  async function uploadFiles(files) {
    setRejected([]);
    for (const file of files) {
      const temp = {
        id: -Date.now() - Math.random(),
        filename: file.name,
        file_type: file.name.split('.').pop().toLowerCase(),
        size_bytes: file.size,
        collection: target,
        status: 'uploading',
        chunk_count: 0,
        created_at: new Date().toISOString(),
      };
      setUploads((list) => [temp, ...list]);
      const form = new FormData();
      form.append('file', file);
      form.append('collection', target);
      try {
        await apiUpload('/knowledge/documents', form);
        setUploads((list) => list.filter((u) => u.id !== temp.id));
      } catch (err) {
        setUploads((list) => list.map((u) => (u.id === temp.id ? { ...u, status: 'failed', error: err.message } : u)));
      }
      await load();
    }
  }

  // Explain why files were refused before upload (frame 2b).
  function rejectFiles(rejections) {
    setRejected(
      rejections.map(({ file, errors }) =>
        errors[0]?.code === 'file-too-large'
          ? `“${file.name}” is ${formatSize(file.size)}; the limit is ${MAX_MB} MB. Split it into smaller files.`
          : `“${file.name}” can’t be added; upload PDF, DOCX, TXT or Markdown.`,
      ),
    );
  }

  // Remove the confirmed document.
  async function confirmRemove() {
    setRemoveBusy(true);
    try {
      await apiDelete(`/knowledge/documents/${removing.id}`);
      notifyDone(`Removed “${removing.filename}”`);
      await load();
    } catch (error) {
      notifyError('The document wasn’t removed.', error);
    } finally {
      setRemoving(null);
      setRemoveBusy(false);
    }
  }

  // Index a failed document again.
  async function retry(doc) {
    try {
      await apiPost(`/knowledge/documents/${doc.id}/retry`);
      await load();
    } catch (error) {
      notifyError('Indexing couldn’t start again.', error);
    }
  }

  if (failed && docs === null) {
    return (
      <div className={classes.page}>
        <h1 className={classes.title}>Knowledge base</h1>
        <ErrorBanner icon={IconDatabaseOff} title="The knowledge base can’t be reached right now." onRetry={load}>
          Uploads are paused; the assistant keeps working without references. Try again in a few
          minutes.
        </ErrorBanner>
      </div>
    );
  }

  const all = [...uploads, ...(docs ?? [])];
  const shown = active === 'all' ? all : all.filter((d) => d.collection === active);
  const counts = { all: docs?.length ?? 0 };
  (docs ?? []).forEach((d) => {
    counts[d.collection] = (counts[d.collection] ?? 0) + 1;
  });
  const indexing = all.filter(isIndexing).length;
  const passages = (docs ?? []).filter((d) => d.status === 'completed').reduce((sum, d) => sum + d.chunk_count, 0);

  return (
    <div className={classes.page}>
      <div className={classes.top}>
        <div>
          <h1 className={classes.title}>Knowledge base</h1>
          <div className={classes.intro}>
            Reference documents the Hiring Assistant and the interview analysis look up when writing
            job descriptions, suggesting questions, checking answers and drafting emails.
          </div>
        </div>
        <div className={classes.indexState}>
          <span className={`${classes.dot} ${indexing ? classes.dotBusy : ''}`} />
          {indexing ? `Indexing ${indexing} document${indexing > 1 ? 's' : ''}…` : `Search index up to date · ${passages} passages`}
        </div>
      </div>

      <div className={classes.warning}>
        <IconShieldLock size={18} color="#C08A1E" style={{ flex: 'none', marginTop: 1 }} />
        <span>
          <b>Don’t upload CVs, interview notes or any personal data here.</b> CVs arrive through each
          job’s application form.
        </span>
      </div>

      <div className={classes.grid}>
        <CollectionNav active={active} counts={counts} onPick={pickCollection} />

        <div className={classes.column}>
          <Dropzone
            className={classes.dropzone}
            onDrop={uploadFiles}
            onReject={rejectFiles}
            maxSize={MAX_MB * 1024 * 1024}
            accept={ACCEPT}
            activateOnClick={false}
            openRef={openRef}
          >
            <Dropzone.Accept>
              <div className={classes.dragging}>
                <IconFileDownload size={30} className={classes.draggingIcon} />
                <div className={classes.draggingText}>Drop the files to add them to {NAME_OF[target]}</div>
              </div>
            </Dropzone.Accept>
            <Dropzone.Reject>
              <div className={classes.dragging}>
                <IconFileX size={30} color="#B03A2E" />
                <div className={classes.draggingText}>Only PDF, DOCX, TXT or Markdown, up to {MAX_MB} MB</div>
              </div>
            </Dropzone.Reject>
            <Dropzone.Idle>
              <div className={classes.dropInner}>
                <span className={classes.dropIcon}>
                  <IconCloudUpload size={26} />
                </span>
                <div className={classes.dropText}>
                  <div className={classes.dropTitle}>
                    Drop files here or{' '}
                    <button type="button" className={classes.choose} onClick={() => openRef.current?.()}>
                      choose files
                    </button>
                  </div>
                  <div className={classes.dropMeta}>
                    PDF, DOCX, TXT or Markdown · up to {MAX_MB} MB each · added to{' '}
                    <b>{NAME_OF[target]}</b>
                  </div>
                </div>
                <div className={classes.target}>
                  <span className={classes.targetLabel}>Add to</span>
                  <Select
                    size="xs"
                    w={190}
                    value={target}
                    onChange={(value) => value && setTarget(value)}
                    data={COLLECTIONS.filter((c) => c.key !== 'all').map((c) => ({ value: c.key, label: c.name }))}
                    allowDeselect={false}
                    aria-label="Collection to add files to"
                  />
                </div>
              </div>
            </Dropzone.Idle>
          </Dropzone>

          {rejected.length > 0 && (
            <ErrorBanner icon={IconFileX} title={`${rejected.length} file${rejected.length > 1 ? 's' : ''} weren’t added.`}>
              {rejected.map((line) => (
                <span key={line} style={{ display: 'block' }}>
                  {line}
                </span>
              ))}
            </ErrorBanner>
          )}

          <div className={classes.card}>
            <div className={classes.tableTop}>
              <div className={classes.tableTitle}>{NAME_OF[active]}</div>
              <div className={classes.tableCount}>
                {shown.length} document{shown.length === 1 ? '' : 's'}
              </div>
            </div>
            {docs === null ? (
              <div className={classes.skeleton} aria-label="Loading">
                <div style={{ height: 52, borderRadius: 8 }} />
                <div style={{ width: '70%' }} />
                <div style={{ width: '85%' }} />
                <div style={{ width: '60%' }} />
              </div>
            ) : shown.length === 0 ? (
              <EmptyState icon={IconBooks} title="No documents here yet">
                Add company policies, previous job profiles or reference documents. The Hiring
                Assistant uses them when it writes job descriptions.
              </EmptyState>
            ) : (
              <>
                <div className={classes.head}>
                  <div>Document</div>
                  <div>Collection</div>
                  <div>Status</div>
                  <div>Passages</div>
                  <div />
                </div>
                {shown.map((doc) => (
                  <DocumentRow key={doc.id} doc={doc} onRemove={setRemoving} onRetry={retry} />
                ))}
              </>
            )}
          </div>

          <RetrievalTest collection={active} />
        </div>
      </div>

      <ConfirmModal
        opened={Boolean(removing)}
        onClose={() => setRemoving(null)}
        title={`Remove “${removing?.filename}”?`}
        confirmLabel="Remove"
        onConfirm={confirmRemove}
        busy={removeBusy}
      >
        Its {removing?.chunk_count} passages are deleted from the search index. Job descriptions
        already written keep their text.
      </ConfirmModal>
    </div>
  );
}
