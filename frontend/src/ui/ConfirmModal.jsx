import Modal from './Modal';
import Button from './Button';

export default function ConfirmModal({ open, title = 'Xác nhận thao tác', description, confirmText = 'Xác nhận', cancelText = 'Hủy', tone = 'danger', loading = false, onClose, onConfirm }) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      actions={(
        <>
          <Button onClick={onClose} disabled={loading}> {cancelText} </Button>
          <Button variant={tone} onClick={onConfirm} disabled={loading}> {loading ? 'Đang xử lý...' : confirmText} </Button>
        </>
      )}
    >
      <p className='modal-description'>{description}</p>
    </Modal>
  );
}
