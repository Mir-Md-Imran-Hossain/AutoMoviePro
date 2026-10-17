(function () {
  console.log('[WAManager Web Bridge] Initializing web adapter for WAManager Pro desktop suite...');

  function getApiBase() {
    const loc = window.location.pathname;
    if (loc.includes('/assets/wamanager/')) {
      return loc.replace(/\/assets\/wamanager\/.*$/, '/admin/api/wamanager.php');
    }
    return '/admin/api/wamanager.php';
  }

  async function callApi(action, data = {}) {
    const url = getApiBase() + '?action=' + encodeURIComponent(action);
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify(data)
      });
      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error('API Error ' + resp.status + ': ' + errText);
      }
      return await resp.json();
    } catch (e) {
      console.error('[WAManager Web Bridge Error] ' + action, e);
      throw e;
    }
  }

  function openWebFileDialog(options = {}) {
    return new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.style.display = 'none';
      if (options.filters && options.filters.length > 0) {
        const exts = options.filters.flatMap(f => f.extensions || []).map(e => e === '*' ? '*/*' : ('.' + e)).join(',');
        input.accept = exts;
      }
      input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) {
          resolve(null);
          return;
        }
        const formData = new FormData();
        formData.append('file', file);
        try {
          const resp = await fetch(getApiBase() + '?action=upload_media', {
            method: 'POST',
            body: formData
          });
          const res = await resp.json();
          if (res.ok) {
            resolve({
              filePath: res.filePath,
              fileName: res.fileName,
              fileSize: res.fileSize,
              fileType: res.fileType
            });
          } else {
            alert('ফাইল আপলোড ব্যর্থ: ' + (res.error || 'অজানা সমস্যা'));
            resolve(null);
          }
        } catch (err) {
          console.error('File upload error:', err);
          alert('ফাইল আপলোডে সমস্যা হয়েছে।');
          resolve(null);
        } finally {
          if (input.parentNode) input.parentNode.removeChild(input);
        }
      };
      input.oncancel = () => {
        resolve(null);
        if (input.parentNode) input.parentNode.removeChild(input);
      };
      document.body.appendChild(input);
      input.click();
    });
  }

  window.electronAPI = {
    // Accounts
    getAccounts: () => callApi('accounts:list'),
    createAccount: (data) => callApi('accounts:create', data),
    connectAccount: (id) => callApi('accounts:connect', { id }),
    disconnectAccount: (id) => callApi('accounts:disconnect', { id }),
    deleteAccount: (id) => callApi('accounts:delete', { id }),
    openWhatsAppWeb: (id) => {
      window.open('https://web.whatsapp.com', '_blank');
      return Promise.resolve(true);
    },
    getCapabilities: () => callApi('accounts:capabilities'),
    grabGroupMembers: (id) => callApi('accounts:grabGroupMembers', { id }),
    grabAllGroups: (id) => callApi('accounts:grabAllGroups', { id }),
    grabChatList: (id) => callApi('accounts:grabChatList', { id }),
    filterNumber: (id, phone) => callApi('accounts:filterNumber', { id, phone }),
    openFileDialog: (options) => openWebFileDialog(options),

    // Contacts
    getContacts: (filter) => callApi('contacts:list', filter),
    createContact: (data) => callApi('contacts:create', data),
    importContacts: (rawRows, options) => callApi('contacts:import', { rawRows, options }),
    setOptOut: (phone, reason) => callApi('contacts:optOut', { phone, reason }),
    deleteContact: (id) => callApi('contacts:delete', { id }),
    syncWhatsAppNames: () => callApi('contacts:syncWhatsAppNames'),
    segregateCountries: () => callApi('contacts:segregateCountries'),
    deleteForeignContacts: () => callApi('contacts:deleteForeign'),

    // Groups
    getGroups: () => callApi('groups:list'),
    createGroup: (name, desc) => callApi('groups:create', { name, desc }),
    addMemberToGroup: (groupId, contactId) => callApi('groups:addMember', { groupId, contactId }),
    addMembersToGroup: (groupId, contactIds) => callApi('groups:addMembers', { groupId, contactIds }),
    addManualNumbersToGroup: (groupId, numbers, defaultCountryCode) => callApi('groups:addManualNumbers', { groupId, numbers, defaultCountryCode }),
    removeMemberFromGroup: (groupId, contactId) => callApi('groups:removeMember', { groupId, contactId }),
    removeMembersFromGroup: (groupId, contactIds) => callApi('groups:removeMembers', { groupId, contactIds }),
    getGroupMembers: (groupId, search) => callApi('groups:members', { groupId, search }),
    deleteGroup: (groupId) => callApi('groups:delete', { groupId }),

    // Templates
    getTemplates: () => callApi('templates:list'),
    createTemplate: (data) => callApi('templates:create', data),
    deleteTemplate: (id) => callApi('templates:delete', { id }),

    // Campaigns
    getCampaigns: () => callApi('campaigns:list'),
    createCampaign: (data) => callApi('campaigns:create', data),
    prepareCampaign: (id) => callApi('campaigns:prepare', { id }),
    startCampaign: (id) => callApi('campaigns:start', { id }),
    pauseCampaign: (id) => callApi('campaigns:pause', { id }),
    resumeCampaign: (id) => callApi('campaigns:resume', { id }),
    cancelCampaign: (id) => callApi('campaigns:cancel', { id }),
    getCampaignJobs: (id) => callApi('campaigns:jobs', { id }),
    stopAllCampaigns: () => callApi('campaigns:stopAll'),

    // Leads
    searchLeads: (cat, loc, lim) => callApi('leads:search', { cat, loc, lim }),
    getSavedLeads: () => callApi('leads:saved'),
    saveLeads: (leads) => callApi('leads:save', { leads }),
    convertLeadToContact: (id) => callApi('leads:convert', { id }),

    // Inbox & Auto-reply
    getInboundMessages: (accId) => callApi('inbox:messages', { accId }),
    sendManualReply: (accId, phone, msg) => callApi('inbox:reply', { accId, phone, msg }),
    receiveMockMessage: (accId, phone, name, msg) => callApi('inbox:receiveMock', { accId, phone, name, msg }),
    getRules: () => callApi('inbox:rules'),
    createRule: (rule) => callApi('inbox:createRule', { rule }),
    toggleRule: (id, active) => callApi('inbox:toggleRule', { id, active }),
    deleteRule: (id) => callApi('inbox:deleteRule', { id }),

    // Reports
    getMetrics: () => callApi('reports:metrics'),
    getLogs: (lim) => callApi('reports:logs', { lim }),
    exportContactsCSV: () => callApi('reports:exportContacts'),

    // Backup & Restore
    createBackup: (dest) => callApi('backups:create', { dest }),
    listBackups: () => callApi('backups:list'),
    restoreBackup: (path) => callApi('backups:restore', { path }),

    // Queue Diagnostics
    getQueueDiagnostics: () => callApi('queue:diagnostics'),

    // Products & Web Scraping
    getProducts: (filter) => callApi('products:list', filter),
    getProductById: (id) => callApi('products:get', { id }),
    createProduct: (data) => callApi('products:create', data),
    updateProduct: (id, data) => callApi('products:update', { id, data }),
    deleteProduct: (id) => callApi('products:delete', { id }),
    getScrapedWebsites: () => callApi('products:scrapedWebsites'),

    // Gemini AI Hub
    getAISettings: () => callApi('ai:getSettings'),
    saveAISettings: (settings) => callApi('ai:saveSettings', { settings }),
    testAIConnection: (key, model) => callApi('ai:testConnection', { key, model }),
    generateAIMarketing: (params) => callApi('ai:generateMarketing', params),
    generateAISmartReply: (params) => callApi('ai:smartReply', params),
    scrapeWebsiteAI: (url) => callApi('ai:scrapeWebsite', { url }),
    paraphraseVariations: (baseMsg, count) => callApi('ai:paraphraseVariations', { baseMsg, count }),

    // Customer Request Automation
    getRequestDispatches: () => callApi('requests:list'),
    triggerCustomerRequest: (params) => callApi('requests:trigger', params),

    // System
    openExternalUrl: (url) => {
      window.open(url, '_blank');
      return Promise.resolve(true);
    }
  };

  console.log('[WAManager Web Bridge] window.electronAPI successfully bound with 52 methods.');
})();
