import nodemailer from 'nodemailer';
import { isEmail } from './contact.mjs';

export function createMailer(env = process.env, createTransport = nodemailer.createTransport) {
  const required = ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASS', 'CONTACT_FROM', 'CONTACT_TO'];
  if (required.some(key => !env[key]?.trim())) return undefined;
  if (!isEmail(env.CONTACT_TO) || !isEmail(env.CONTACT_FROM)) throw new Error('CONTACT_TO and CONTACT_FROM must each be a single email address.');
  const port = Number(env.SMTP_PORT || 587);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid SMTP_PORT.');
  if (env.SMTP_SECURE && !['true', 'false'].includes(env.SMTP_SECURE)) throw new Error('SMTP_SECURE must be true or false.');
  const secure = env.SMTP_SECURE ? env.SMTP_SECURE === 'true' : port === 465;
  const transport = createTransport({
    host: env.SMTP_HOST, port, secure, requireTLS: !secure,
    auth: { user: env.SMTP_USER, pass: env.SMTP_PASS },
    tls: { minVersion: 'TLSv1.2' },
    connectionTimeout: 5000, greetingTimeout: 5000, socketTimeout: 10000, dnsTimeout: 5000,
    disableFileAccess: true, disableUrlAccess: true,
    logger: false, debug: false
  });
  return async data => {
    const result = await transport.sendMail({
      from: { name: 'Portfolio contact', address: env.CONTACT_FROM },
      to: env.CONTACT_TO,
      replyTo: { name: data.name, address: data.email },
      subject: `[Portfolio] ${data.subject || 'New message'}`,
      text: `Name: ${data.name}\nEmail: ${data.email}\n\n${data.message}`
    });
    if (!result.accepted?.length) throw new Error('SMTP server did not accept the message.');
  };
}
