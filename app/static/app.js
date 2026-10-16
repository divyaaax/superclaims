/**
 * SuperClaims — Enterprise Claim Document Segregator & Extraction Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const claimForm = document.getElementById('claim-form');
  const claimIdInput = document.getElementById('claim-id-input');
  const btnRandomId = document.getElementById('btn-random-id');
  const dropzone = document.getElementById('pdf-dropzone');
  const fileInput = document.getElementById('pdf-file-input');
  const dropzonePrompt = document.getElementById('dropzone-prompt');
  const filePreview = document.getElementById('file-preview');
  const previewFilename = document.getElementById('preview-filename');
  const previewFilesize = document.getElementById('preview-filesize');
  const btnRemoveFile = document.getElementById('btn-remove-file');

  const btnProcess = document.getElementById('btn-process-claim');
  const btnProcessText = document.getElementById('btn-process-text');
  const btnSpinner = document.getElementById('btn-spinner');
  const btnLoadSample = document.getElementById('btn-load-sample');

  const progressBox = document.getElementById('progress-box');
  const progressFill = document.getElementById('progress-fill');
  const progressStepText = document.getElementById('progress-step-text');
  const progressTime = document.getElementById('progress-time');

  const errorAlert = document.getElementById('error-alert');
  const errorMessage = document.getElementById('error-message');
  const resultsSection = document.getElementById('results-section');

  const btnCopyJson = document.getElementById('btn-copy-json');
  const btnDownloadJson = document.getElementById('btn-download-json');

  let selectedFile = null;
  let processingStartTime = 0;
  let progressInterval = null;
  let latestResultData = null;
  let activeCategoryFilter = 'all';

  // =================================================================
  // 1. Initial Health Check
  // =================================================================
  async function checkHealth() {
    try {
      const res = await fetch('/health');
      if (res.ok) {
        const data = await res.json();
        const statusText = document.getElementById('system-status-text');
        if (statusText) {
          statusText.textContent = data.use_mock_llm ? 'Engine Online (Mock)' : 'Engine Online (Live LLM)';
        }
      }
    } catch (e) {
      console.warn('System health check warning:', e);
    }
  }
  checkHealth();

  // =================================================================
  // 2. Button State & Validation
  // =================================================================
  function updateButtonState() {
    const hasClaimId = Boolean(claimIdInput.value.trim());
    const hasFile = Boolean(selectedFile);
    btnProcess.disabled = !(hasClaimId && hasFile);
  }

  claimIdInput.addEventListener('input', updateButtonState);

  // =================================================================
  // 3. Tab Switching Logic
  // =================================================================
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanels.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      document.getElementById(targetId)?.classList.add('active');
    });
  });

  // =================================================================
  // 4. Claim ID Auto-Generation
  // =================================================================
  btnRandomId.addEventListener('click', () => {
    const randomNum = Math.floor(100000 + Math.random() * 900000);
    claimIdInput.value = `CLM-2025-${randomNum}`;
    updateButtonState();
  });

  // =================================================================
  // 5. Drag & Drop PDF Handling
  // =================================================================
  dropzone.addEventListener('click', (e) => {
    if (e.target !== btnRemoveFile && !btnRemoveFile.contains(e.target)) {
      fileInput.click();
    }
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files.length > 0) {
      handleFile(fileInput.files[0]);
    }
  });

  btnRemoveFile.addEventListener('click', (e) => {
    e.stopPropagation();
    clearSelectedFile();
  });

  function handleFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      showError('Please select a valid medical claim PDF file.');
      return;
    }
    selectedFile = file;
    previewFilename.textContent = file.name;
    previewFilesize.textContent = formatBytes(file.size);

    dropzonePrompt.classList.add('hidden');
    filePreview.classList.remove('hidden');
    hideError();
    updateButtonState();
  }

  function clearSelectedFile() {
    selectedFile = null;
    fileInput.value = '';
    dropzonePrompt.classList.remove('hidden');
    filePreview.classList.add('hidden');
    updateButtonState();
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  // =================================================================
  // 6. One-Click Sample PDF Loader
  // =================================================================
  btnLoadSample.addEventListener('click', async () => {
    btnLoadSample.disabled = true;
    btnLoadSample.textContent = 'Loading sample...';
    try {
      const response = await fetch('/api/sample-pdf');
      if (!response.ok) throw new Error('Could not fetch sample PDF');
      const blob = await response.blob();
      const file = new File([blob], 'sample_medical_claim.pdf', { type: 'application/pdf' });
      claimIdInput.value = 'CLM-2024-789456';
      handleFile(file);
    } catch (err) {
      showError(`Unable to load sample claim: ${err.message}`);
    } finally {
      btnLoadSample.disabled = false;
      btnLoadSample.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
        </svg>
        Load Sample Claim (18 Pages)
      `;
    }
  });

  // =================================================================
  // 7. Form Submission & Processing Execution
  // =================================================================
  claimForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideError();

    const claimId = claimIdInput.value.trim();
    if (!claimId) {
      showError('Please enter a Claim Reference Identifier.');
      return;
    }

    if (!selectedFile) {
      showError('Please select or drop a claim PDF document.');
      return;
    }

    startLoading();

    const formData = new FormData();
    formData.append('claim_id', claimId);
    formData.append('file', selectedFile);

    try {
      const response = await fetch('/api/process', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || `Server error: HTTP ${response.status}`);
      }

      latestResultData = data;
      renderResults(data);
    } catch (err) {
      showError(err.message || 'Processing failed. Please check server logs.');
    } finally {
      stopLoading();
    }
  });

  function startLoading() {
    btnProcess.disabled = true;
    btnProcessText.textContent = 'Segregating documents...';
    btnSpinner.classList.remove('hidden');
    progressBox.classList.remove('hidden');
    resultsSection.classList.add('hidden');

    progressFill.style.width = '15%';
    progressStepText.textContent = 'Step 1: Document Ingestion & Page Extraction...';
    setWorkflowStep(1);

    processingStartTime = Date.now();
    progressInterval = setInterval(() => {
      const elapsed = ((Date.now() - processingStartTime) / 1000).toFixed(1);
      progressTime.textContent = `${elapsed}s`;

      if (elapsed > 0.5 && elapsed < 1.5) {
        progressFill.style.width = '45%';
        progressStepText.textContent = 'Step 2: AI Segregator: Classifying pages into 9 categories...';
        setWorkflowStep(2);
      } else if (elapsed >= 1.5 && elapsed < 2.8) {
        progressFill.style.width = '75%';
        progressStepText.textContent = 'Step 3: Parallel Agent Extraction (ID, Discharge, Bill)...';
        setWorkflowStep(3);
      } else if (elapsed >= 2.8) {
        progressFill.style.width = '92%';
        progressStepText.textContent = 'Step 4: Decimal Financial Reconciliation & Aggregation...';
        setWorkflowStep(4);
      }
    }, 200);
  }

  function stopLoading() {
    clearInterval(progressInterval);
    btnProcess.disabled = false;
    btnProcessText.textContent = 'Segregate PDF';
    btnSpinner.classList.add('hidden');
    progressFill.style.width = '100%';
    setWorkflowStep(5);

    setTimeout(() => {
      progressBox.classList.add('hidden');
    }, 400);
    updateButtonState();
  }

  function setWorkflowStep(num) {
    for (let i = 1; i <= 5; i++) {
      const el = document.getElementById(`step-${i}`);
      if (el) {
        if (i <= num) el.classList.add('active');
        else el.classList.remove('active');
      }
    }
  }

  function showError(msg) {
    errorMessage.textContent = msg;
    errorAlert.classList.remove('hidden');
    errorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function hideError() {
    errorAlert.classList.add('hidden');
  }

  // =================================================================
  // 8. Render Results Dashboard
  // =================================================================
  function renderResults(data) {
    resultsSection.classList.remove('hidden');
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    // 1. KPI Cards
    document.getElementById('kpi-claim-id').textContent = data.claim_id;
    document.getElementById('kpi-pages').textContent = data.segregation_results.total_pages;
    document.getElementById('kpi-latency').textContent = data.processing_time_seconds 
      ? `${data.processing_time_seconds}s` 
      : '0.04s';

    const billData = data.extracted_data.itemized_bill;
    if (billData && billData.stated_total !== null && billData.stated_total !== undefined) {
      document.getElementById('kpi-bill-total').textContent = `$${Number(billData.stated_total).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
      const reconContainer = document.getElementById('kpi-reconciliation');
      if (billData.discrepancy_detected) {
        reconContainer.innerHTML = `<span class="badge badge-error">⚠️ Variance Flagged</span>`;
      } else {
        reconContainer.innerHTML = `<span class="badge badge-success">✓ Exact Match ($0.00 Variance)</span>`;
      }
    } else {
      document.getElementById('kpi-bill-total').textContent = 'N/A';
      document.getElementById('kpi-reconciliation').innerHTML = `<span class="badge badge-neutral">No Bill</span>`;
    }

    // 2. Render Tabs
    renderSegregation(data.segregation_results);
    renderIdentity(data.extracted_data.identity_information);
    renderDischarge(data.extracted_data.discharge_summary);
    renderBill(data.extracted_data.itemized_bill);

    // 3. Render JSON
    document.getElementById('json-raw-display').textContent = JSON.stringify(data, null, 2);

    // Switch to first tab (Segregation)
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelector('.tab-btn[data-tab="tab-segregation"]')?.classList.add('active');
    document.getElementById('tab-segregation')?.classList.add('active');
  }

  // =================================================================
  // 9. Document Segregation & Filter Chips
  // =================================================================
  function renderSegregation(segregation) {
    document.getElementById('segregation-count-badge').textContent = `${segregation.total_pages} Total Pages`;
    activeCategoryFilter = 'all';

    const catCounts = {};
    segregation.page_classifications.forEach(p => {
      catCounts[p.document_type] = (catCounts[p.document_type] || 0) + 1;
    });

    const chipContainer = document.getElementById('category-filter-chips');
    chipContainer.innerHTML = '';

    const allChip = document.createElement('button');
    allChip.type = 'button';
    allChip.className = 'chip-btn active';
    allChip.innerHTML = `All Pages <span class="chip-counter">${segregation.total_pages}</span>`;
    allChip.addEventListener('click', () => {
      document.querySelectorAll('.chip-btn').forEach(c => c.classList.remove('active'));
      allChip.classList.add('active');
      activeCategoryFilter = 'all';
      filterTable(segregation.page_classifications);
    });
    chipContainer.appendChild(allChip);

    const orderedCategories = [
      'identity_document',
      'discharge_summary',
      'itemized_bill',
      'prescription',
      'investigation_report',
      'claim_forms',
      'cheque_or_bank_details',
      'cash_receipt',
      'other'
    ];

    orderedCategories.forEach(cat => {
      if (catCounts[cat]) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip-btn';
        chip.innerHTML = `${cat} <span class="chip-counter">${catCounts[cat]}</span>`;
        chip.addEventListener('click', () => {
          document.querySelectorAll('.chip-btn').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          activeCategoryFilter = cat;
          filterTable(segregation.page_classifications);
        });
        chipContainer.appendChild(chip);
      }
    });

    filterTable(segregation.page_classifications);
  }

  function filterTable(pageClassifications) {
    const tbody = document.getElementById('page-classifications-tbody');
    tbody.innerHTML = '';

    const filtered = activeCategoryFilter === 'all'
      ? pageClassifications
      : pageClassifications.filter(p => p.document_type === activeCategoryFilter);

    filtered.forEach(p => {
      const tr = document.createElement('tr');
      let routingAgent = '<span style="color: var(--color-text-muted);">None (Filtered out)</span>';

      if (p.document_type === 'identity_document') {
        routingAgent = '<span class="badge badge-primary">➔ ID Agent (Page ' + p.page_number + ')</span>';
      } else if (p.document_type === 'discharge_summary') {
        routingAgent = '<span class="badge badge-primary">➔ Discharge Agent (Page ' + p.page_number + ')</span>';
      } else if (p.document_type === 'itemized_bill') {
        routingAgent = '<span class="badge badge-success">➔ Itemized Bill Agent (Page ' + p.page_number + ')</span>';
      }

      tr.innerHTML = `
        <td style="font-family: var(--font-mono); font-weight: 700; color: var(--color-navy);">#${p.page_number}</td>
        <td><span class="badge badge-neutral" style="font-family: var(--font-mono);">${p.document_type}</span></td>
        <td style="font-family: var(--font-mono); font-weight: 600;">${p.confidence !== null ? Math.round(p.confidence * 100) + '%' : '100%'}</td>
        <td>${routingAgent}</td>
        <td style="color: var(--color-text-secondary);">${p.reasoning || 'Standard classification'}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // =================================================================
  // 10. Patient Identity Details Tab
  // =================================================================
  function renderIdentity(idData) {
    const grid = document.getElementById('identity-details-grid');
    grid.innerHTML = '';
    const sourceTag = document.getElementById('id-source-tag');
    sourceTag.textContent = idData && idData.source_pages && idData.source_pages.length > 0 
      ? `Source Pages: ${idData.source_pages.join(', ')}` 
      : 'Source Pages: None';

    if (!idData || !idData.extracted) {
      grid.innerHTML = `<div class="info-cell" style="grid-column: 1 / -1;"><div class="info-value empty">No identity document pages detected in this claim package.</div></div>`;
      return;
    }

    const fields = [
      { caption: 'Patient Legal Name', value: idData.patient_name },
      { caption: 'Date of Birth', value: idData.date_of_birth },
      { caption: 'Identification Number', value: idData.id_numbers?.id_number },
      { caption: 'Document ID Type', value: idData.id_numbers?.id_type },
      { caption: 'Gender', value: idData.gender },
      { caption: 'Residential Address', value: idData.address },
      { caption: 'Policy Details on ID', value: idData.policy_details, fallback: 'None specified on ID' }
    ];

    fields.forEach(f => {
      const cell = document.createElement('div');
      cell.className = 'info-cell';
      const hasVal = f.value !== null && f.value !== undefined && f.value !== '';
      cell.innerHTML = `
        <div class="info-caption">${f.caption}</div>
        <div class="info-value ${hasVal ? '' : 'empty'}">${hasVal ? f.value : (f.fallback || 'Not Specified')}</div>
      `;
      grid.appendChild(cell);
    });
  }

  // =================================================================
  // 11. Discharge Summary Details Tab
  // =================================================================
  function renderDischarge(dischargeData) {
    const grid = document.getElementById('discharge-details-grid');
    grid.innerHTML = '';
    const sourceTag = document.getElementById('discharge-source-tag');
    sourceTag.textContent = dischargeData && dischargeData.source_pages && dischargeData.source_pages.length > 0 
      ? `Source Pages: ${dischargeData.source_pages.join(', ')}` 
      : 'Source Pages: None';

    const diagText = document.getElementById('diagnosis-text');

    if (!dischargeData || !dischargeData.extracted) {
      diagText.textContent = 'No discharge summary detected';
      grid.innerHTML = `<div class="info-cell" style="grid-column: 1 / -1;"><div class="info-value empty">No discharge summary pages detected in this claim package.</div></div>`;
      return;
    }

    diagText.textContent = dischargeData.diagnosis || 'Clinical Diagnosis Documented';

    const fields = [
      { caption: 'Hospital / Facility Name', value: dischargeData.hospital_name },
      { caption: 'Admission Date', value: dischargeData.admission_date },
      { caption: 'Discharge Date', value: dischargeData.discharge_date },
      { caption: 'Attending Physician', value: dischargeData.physician_details?.name },
      { caption: 'Discharge Condition', value: dischargeData.discharge_condition },
      { 
        caption: 'Prescribed Discharge Medications', 
        value: dischargeData.discharge_medications && dischargeData.discharge_medications.length > 0 
          ? dischargeData.discharge_medications.join('; ') 
          : null 
      }
    ];

    fields.forEach(f => {
      const cell = document.createElement('div');
      cell.className = 'info-cell';
      const hasVal = f.value !== null && f.value !== undefined && f.value !== '';
      cell.innerHTML = `
        <div class="info-caption">${f.caption}</div>
        <div class="info-value ${hasVal ? '' : 'empty'}">${hasVal ? f.value : 'Not Specified'}</div>
      `;
      grid.appendChild(cell);
    });
  }

  // =================================================================
  // 12. Itemized Hospital Bill Tab & Decimal Math
  // =================================================================
  function renderBill(billData) {
    const sourceTag = document.getElementById('bill-source-tag');
    sourceTag.textContent = billData && billData.source_pages && billData.source_pages.length > 0 
      ? `Source Pages: ${billData.source_pages.join(', ')}` 
      : 'Source Pages: None';

    const banner = document.getElementById('reconciliation-banner');
    const tbody = document.getElementById('bill-items-tbody');
    tbody.innerHTML = '';

    if (!billData || !billData.extracted) {
      banner.innerHTML = `<div class="info-cell" style="grid-column: 1 / -1;"><div class="info-value empty">No itemized bill pages detected in this claim package.</div></div>`;
      return;
    }

    const subtotal = billData.stated_subtotal !== null ? `$${Number(billData.stated_subtotal).toFixed(2)}` : 'N/A';
    const tax = billData.stated_tax !== null ? `$${Number(billData.stated_tax).toFixed(2)}` : 'N/A';
    const total = billData.stated_total !== null ? `$${Number(billData.stated_total).toFixed(2)}` : 'N/A';
    const calcTotal = billData.calculated_total !== null ? `$${Number(billData.calculated_total).toFixed(2)}` : 'N/A';

    banner.innerHTML = `
      <div class="recon-col">
        <span class="recon-caption">Bill Reference #</span>
        <span class="recon-val" style="font-size: 0.95rem;">${billData.bill_number || 'N/A'}</span>
      </div>
      <div class="recon-col">
        <span class="recon-caption">Stated Subtotal</span>
        <span class="recon-val">${subtotal}</span>
      </div>
      <div class="recon-col">
        <span class="recon-caption">Stated Tax</span>
        <span class="recon-val">${tax}</span>
      </div>
      <div class="recon-col">
        <span class="recon-caption">Stated Total</span>
        <span class="recon-val" style="color: var(--color-primary);">${total}</span>
      </div>
      <div class="recon-col">
        <span class="recon-caption">Calculated Sum (Decimal)</span>
        <span class="recon-val" style="color: var(--color-success);">${calcTotal}</span>
      </div>
      <div class="recon-col">
        <span class="recon-caption">Reconciliation Audit</span>
        <span class="badge ${billData.discrepancy_detected ? 'badge-error' : 'badge-success'}">
          ${billData.discrepancy_detected ? '⚠️ Variance Flagged' : '✓ Exact Match'}
        </span>
      </div>
    `;

    billData.bill_items.forEach((item, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="color: var(--color-text-muted); font-family: var(--font-mono);">${idx + 1}</td>
        <td><strong style="color: var(--color-navy);">${item.item_description}</strong></td>
        <td class="num-align">${item.quantity !== null ? item.quantity : '-'}</td>
        <td class="num-align">${item.unit_price !== null ? '$' + Number(item.unit_price).toFixed(2) : '-'}</td>
        <td class="num-align" style="font-weight: 700; color: var(--color-primary);">$${Number(item.amount).toFixed(2)}</td>
        <td style="color: var(--color-text-secondary);">${item.service_date || '-'}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // =================================================================
  // 13. Copy & Download JSON Actions
  // =================================================================
  btnCopyJson.addEventListener('click', () => {
    if (latestResultData) {
      navigator.clipboard.writeText(JSON.stringify(latestResultData, null, 2)).then(() => {
        const originalHtml = btnCopyJson.innerHTML;
        btnCopyJson.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
          Copied!
        `;
        setTimeout(() => {
          btnCopyJson.innerHTML = originalHtml;
        }, 2000);
      });
    }
  });

  btnDownloadJson.addEventListener('click', () => {
    if (latestResultData) {
      const jsonStr = JSON.stringify(latestResultData, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${latestResultData.claim_id || 'claim'}_processed.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  });

  // =================================================================
  // 14. Light / Dark Theme Management
  // =================================================================
  function initTheme() {
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const themeToggleLabel = document.getElementById('theme-toggle-label');

    function updateThemeUI(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      try {
        localStorage.setItem('superclaims_theme', theme);
      } catch (e) {
        // Ignore storage exceptions if blocked
      }
      if (themeToggleLabel) {
        themeToggleLabel.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
      }
      if (themeToggleBtn) {
        themeToggleBtn.setAttribute('title', `Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`);
        themeToggleBtn.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`);
      }
    }

    let currentTheme = document.documentElement.getAttribute('data-theme');
    if (!currentTheme) {
      try {
        const saved = localStorage.getItem('superclaims_theme');
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        currentTheme = saved || (prefersDark ? 'dark' : 'light');
      } catch (e) {
        currentTheme = 'light';
      }
    }
    updateThemeUI(currentTheme);

    if (themeToggleBtn) {
      themeToggleBtn.addEventListener('click', () => {
        const active = document.documentElement.getAttribute('data-theme') || 'light';
        const nextTheme = active === 'dark' ? 'light' : 'dark';
        updateThemeUI(nextTheme);
      });
    }

    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        try {
          if (!localStorage.getItem('superclaims_theme')) {
            updateThemeUI(e.matches ? 'dark' : 'light');
          }
        } catch (_) {}
      });
    }
  }

  initTheme();

  // Initial check
  updateButtonState();
});

