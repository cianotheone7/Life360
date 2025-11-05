(function () {
  // Fail-safe global confirm for forms with class "js-confirm-form"
  const modal  = document.getElementById('globalConfirmModal');
  const text   = document.getElementById('globalConfirmText');
  const title  = document.getElementById('globalConfirmTitle');
  const btnOk  = document.getElementById('gcConfirm');
  const btnNo  = document.getElementById('gcCancel');
  const backd  = document.getElementById('gcBackdrop');
  let pendingForm = null;

  function openConfirm(form){
    if (!modal || !text || !title || !btnOk) return false; // don't block submit if modal missing
    pendingForm = form;
    text.textContent  = form.getAttribute('data-confirm') || 'Are you sure?';
    title.textContent = form.getAttribute('data-confirm-title') || 'Confirm action';
    btnOk.textContent = form.getAttribute('data-confirm-label') || 'Confirm';
    modal.removeAttribute('hidden'); modal.style.display = 'grid';
    if (backd) { backd.removeAttribute('hidden'); backd.style.display = 'block'; }
    return true;
  }
  function closeConfirm(){
    if (modal) { modal.setAttribute('hidden','hidden'); modal.style.display='none'; }
    if (backd) { backd.setAttribute('hidden','hidden'); backd.style.display='none'; }
    pendingForm = null;
  }
  if (btnNo)  btnNo.addEventListener('click',  closeConfirm);
  if (backd)  backd.addEventListener('click',  closeConfirm);
  if (btnOk)  btnOk.addEventListener('click', function(){
    if (pendingForm) pendingForm.submit();
    closeConfirm();
  });
  document.addEventListener('submit', function(ev){
    const f = ev.target;
    if (f && f.classList && f.classList.contains('js-confirm-form') && f.dataset.confirmed !== '1') {
      const opened = openConfirm(f);
      if (opened) { ev.preventDefault(); return false; }
    }
  }, true);
})();