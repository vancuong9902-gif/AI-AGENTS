import multer from 'multer';
import path from 'path';
import fs from 'fs';
import { ApiError } from '../utils/ApiError.js';

const uploadDir = process.env.UPLOAD_DIR ?? './uploads';
const maxSize = Number(process.env.MAX_PDF_SIZE_MB ?? 50) * 1024 * 1024;

if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, uploadDir),
  filename: (_req, file, cb) => {
    const safe = path.basename(file.originalname).replace(/[^a-zA-Z0-9._-]/g, '_');
    cb(null, `${Date.now()}-${safe}`);
  }
});

export const pdfUpload = multer({
  storage,
  limits: { fileSize: maxSize },
  fileFilter: (_req, file, cb) => {
    if (file.mimetype !== 'application/pdf') {
      cb(new ApiError(400, 'Chỉ chấp nhận tệp PDF'));
      return;
    }
    cb(null, true);
  }
});

export const validatePdfMagic = async (filepath: string) => {
  const fd = await fs.promises.open(filepath, 'r');
  const buffer = Buffer.alloc(4);
  await fd.read(buffer, 0, 4, 0);
  await fd.close();
  if (buffer.toString() !== '%PDF') {
    throw new ApiError(400, 'Tệp PDF không hợp lệ');
  }
};
