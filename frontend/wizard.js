/* Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
   SPDX-License-Identifier: MIT-0 */
let currentStep = 0;
const totalSteps = 5;

function goToStep(step) {
    if (step < 0 || step >= totalSteps) return;
    document.querySelectorAll('.step-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.step-indicator').forEach(s => {
        s.classList.remove('active');
        if (parseInt(s.dataset.step) < step) s.classList.add('completed');
        else s.classList.remove('completed');
    });
    document.getElementById('step-' + step).classList.add('active');
    document.querySelector(`.step-indicator[data-step="${step}"]`).classList.add('active');
    currentStep = step;
    if (step === 4) generateCli();
    window.scrollTo(0, 0);
}

function nextStep() { goToStep(currentStep + 1); }
function prevStep() { goToStep(currentStep - 1); }

function toggleCompanyIdFields() {
    const isSoleProp = document.getElementById('businessType').value === 'SOLE_PROPRIETOR';
    document.getElementById('companyIdFields').classList.toggle('hidden', isSoleProp);
}

function updateCharCount(el, countId) {
    document.getElementById(countId).textContent = el.value.length + ' / ' + el.maxLength;
}

function esc(val) {
    if (!val) return '';
    return val.replace(/'/g, "'\\''");
}

function generateCli() {
    const v = id => (document.getElementById(id)?.value || '').trim();
    const lines = [];

    function comment(text) { lines.push(`\n# ${'='.repeat(60)}\n# ${text}\n# ${'='.repeat(60)}`); }
    function cmd(text) { lines.push(text); }
    function note(text) { lines.push(`\n# NOTE: ${text}`); }

    // ---- CREATE REGISTRATION ----
    comment('STEP 1: Create Toll-Free Registration');
    cmd(`aws pinpoint-sms-voice-v2 create-registration \\
    --registration-type US_TOLL_FREE_REGISTRATION \\
    --tags "Key=Name,Value=${esc(v('companyName'))}-TollFree"
`);
    note('Save the RegistrationId from the response. Replace TFN_REG_ID below.');

    // ---- REQUEST PHONE NUMBER ----
    comment('STEP 2: Request a Toll-Free Phone Number');
    note('You must purchase the toll-free number BEFORE submitting the registration (ASSOCIATE_BEFORE_SUBMIT).');
    note('You are charged the monthly lease fee immediately.');
    cmd(`aws pinpoint-sms-voice-v2 request-phone-number \\
    --iso-country-code US \\
    --message-type ${v('phoneMessageType')} \\
    --number-capabilities SMS \\
    --number-type TOLL_FREE`);
    note('Save the PhoneNumberId from the response. Replace PHONE_NUMBER_ID below.');

    // ---- ASSOCIATE PHONE NUMBER ----
    comment('STEP 3: Associate Phone Number with Registration');
    note('ASSOCIATE_BEFORE_SUBMIT — must be done before submitting.');
    cmd(`aws pinpoint-sms-voice-v2 create-registration-association \\
    --registration-id TFN_REG_ID \\
    --resource-id PHONE_NUMBER_ID`);

    // ---- POPULATE FIELDS ----
    comment('STEP 4: Populate Registration Fields');

    // companyInfo
    cmd(`# companyInfo.companyName
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.companyName \\
    --text-value '${esc(v('companyName'))}'`);

    cmd(`\n# companyInfo.website
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.website \\
    --text-value '${esc(v('website'))}'`);

    cmd(`\n# companyInfo.address1
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.address1 \\
    --text-value '${esc(v('address1'))}'`);

    if (v('address2')) {
        cmd(`\n# companyInfo.address2
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.address2 \\
    --text-value '${esc(v('address2'))}'`);
    }

    cmd(`\n# companyInfo.city
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.city \\
    --text-value '${esc(v('city'))}'`);

    cmd(`\n# companyInfo.state
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.state \\
    --text-value '${esc(v('state'))}'`);

    cmd(`\n# companyInfo.zipCode
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.zipCode \\
    --text-value '${esc(v('zipCode'))}'`);

    cmd(`\n# companyInfo.isoCountryCode
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.isoCountryCode \\
    --text-value '${esc(v('country').toUpperCase())}'`);

    cmd(`\n# companyInfo.businessType
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.businessType \\
    --select-choices '${esc(v('businessType'))}'`);

    if (v('businessType') !== 'SOLE_PROPRIETOR') {
        if (v('companyIdNumber')) {
            cmd(`\n# companyInfo.taxId
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.taxId \\
    --text-value '${esc(v('companyIdNumber'))}'`);
        }
        if (v('companyIdType')) {
            cmd(`\n# companyInfo.taxIdAuthority
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.taxIdAuthority \\
    --select-choices '${esc(v('companyIdType'))}'`);
        }
        if (v('companyIdCountry')) {
            cmd(`\n# companyInfo.taxIdCountry
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path companyInfo.taxIdCountry \\
    --text-value '${esc(v('companyIdCountry').toUpperCase())}'`);
        }
    }

    // contactInfo
    cmd(`\n# contactInfo.firstName
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path contactInfo.firstName \\
    --text-value '${esc(v('firstName'))}'`);

    cmd(`\n# contactInfo.lastName
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path contactInfo.lastName \\
    --text-value '${esc(v('lastName'))}'`);

    cmd(`\n# contactInfo.supportEmail
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path contactInfo.supportEmail \\
    --text-value '${esc(v('supportEmail'))}'`);

    cmd(`\n# contactInfo.supportPhoneNumber
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path contactInfo.supportPhoneNumber \\
    --text-value '${esc(v('supportPhoneNumber'))}'`);

    // messagingUseCase
    cmd(`\n# messagingUseCase.monthlyMessageVolume
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.monthlyMessageVolume \\
    --select-choices '${esc(v('monthlyMessageVolume'))}'`);

    cmd(`\n# messagingUseCase.useCaseCategory
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.useCaseCategory \\
    --select-choices '${esc(v('useCaseCategory'))}'`);

    cmd(`\n# messagingUseCase.useCaseDetails
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.useCaseDetails \\
    --text-value '${esc(v('useCaseDetails'))}'`);

    cmd(`\n# messagingUseCase.privacyPolicyUrl
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.privacyPolicyUrl \\
    --text-value '${esc(v('privacyPolicyUrl'))}'`);

    cmd(`\n# messagingUseCase.termsAndConditionsUrl
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.termsAndConditionsUrl \\
    --text-value '${esc(v('termsAndConditionsUrl'))}'`);

    cmd(`\n# messagingUseCase.optInType
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.optInType \\
    --select-choices '${esc(v('optInType'))}'`);

    cmd(`\n# messagingUseCase.optInDescription
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.optInDescription \\
    --text-value '${esc(v('optInWorkflow'))}'`);

    if (v('optInImageS3')) {
        cmd(`\n# Create opt-in image attachment
aws pinpoint-sms-voice-v2 create-registration-attachment \\
    --attachment-url ${esc(v('optInImageS3'))}`);
        note('Save the RegistrationAttachmentId. Replace ATTACHMENT_ID below.');
        cmd(`\n# messagingUseCase.optInImage
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messagingUseCase.optInImage \\
    --registration-attachment-id ATTACHMENT_ID`);
    }

    // messageSamples
    for (let i = 1; i <= 3; i++) {
        const sample = v('messageSample' + i);
        if (sample) {
            cmd(`\n# messageSamples.messageSample${i}
aws pinpoint-sms-voice-v2 put-registration-field-value \\
    --registration-id TFN_REG_ID \\
    --field-path messageSamples.messageSample${i} \\
    --text-value '${esc(sample)}'`);
        }
    }

    // ---- SUBMIT ----
    comment('STEP 5: Submit Registration');
    cmd(`aws pinpoint-sms-voice-v2 submit-registration-version \\
    --registration-id TFN_REG_ID`);
    note('Toll-free registration review typically takes 1-2 weeks.');
    cmd(`\n# Check status:
aws pinpoint-sms-voice-v2 describe-registrations \\
    --registration-ids TFN_REG_ID`);

    // ---- TEST MESSAGE ----
    comment('STEP 6: Send a Test Message (after approval)');
    cmd(`aws pinpoint-sms-voice-v2 send-text-message \\
    --destination-phone-number "+12065550142" \\
    --origination-identity "PHONE_NUMBER_ID_OR_E164" \\
    --message-body '${esc(v('messageSample1') || 'Your verification code is 123456.')}' \\
    --message-type ${v('phoneMessageType')}`);

    // Render
    const container = document.getElementById('cliOutput');
    container.textContent = '';
    const block = document.createElement('div');
    block.className = 'cli-block';
    block.id = 'allCliCommands';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = 'Copy All';
    copyBtn.addEventListener('click', copyAllCli);
    block.appendChild(copyBtn);

    for (const line of lines) {
        const span = document.createElement('span');
        if (line.startsWith('\n# =') || line.startsWith('# =') ||
            line.startsWith('\n# ') || line.startsWith('# ')) {
            span.className = 'comment';
        }
        span.textContent = line;
        block.appendChild(span);
        block.appendChild(document.createTextNode('\n'));
    }
    container.appendChild(block);
}

function copyAllCli() {
    const el = document.getElementById('allCliCommands');
    const text = el.innerText.replace('Copy All', '').trim();
    navigator.clipboard.writeText(text).then(() => {
        const btn = el.querySelector('.copy-btn');
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy All', 2000);
    });
}

// ============================================================
// Event wiring
//
// All handlers are attached here rather than with inline onclick /
// oninput / onchange attributes so the page can run under a
// Content-Security-Policy without 'unsafe-inline' in script-src.
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-goto-step]').forEach(el => {
        el.addEventListener('click', () => goToStep(parseInt(el.dataset.gotoStep, 10)));
    });

    const actions = {
        next: nextStep,
        prev: prevStep,
        'copy-all': copyAllCli,
        'toggle-company-id': toggleCompanyIdFields,
    };
    document.querySelectorAll('[data-action]').forEach(el => {
        const fn = actions[el.dataset.action];
        if (!fn) return;
        const evt = el.tagName === 'SELECT' ? 'change' : 'click';
        el.addEventListener(evt, fn);
    });

    document.querySelectorAll('[data-char-count]').forEach(el => {
        el.addEventListener('input', () => updateCharCount(el, el.dataset.charCount));
    });
});
