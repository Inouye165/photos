import React, { useState, useEffect } from 'react';
import { X, Smartphone, Wifi, Copy, Check, ExternalLink, ShieldCheck } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { fetchNetworkInfo } from '../api';

export default function MobileConnectModal({ isOpen, onClose }) {
  const [networkInfo, setNetworkInfo] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchNetworkInfo()
        .then((data) => setNetworkInfo(data))
        .catch(console.error);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const primaryUrl = networkInfo?.primary_url || window.location.origin;

  const handleCopy = () => {
    navigator.clipboard.writeText(primaryUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ maxWidth: '520px', textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Smartphone size={22} color="#10b981" />
            <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.3rem', color: '#ffffff' }}>
              Connect Phone or Network Device
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px' }}
          >
            <X size={20} />
          </button>
        </div>

        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginBottom: '1.5rem', lineHeight: '1.4' }}>
          Scan the QR code with your phone camera or open the URL below to pair a device on your home Wi-Fi network.
        </p>

        {/* QR Code Container */}
        <div style={{
          display: 'inline-flex',
          padding: '1.25rem',
          background: '#ffffff',
          borderRadius: '16px',
          boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
          marginBottom: '1.5rem'
        }}>
          <QRCodeSVG
            value={primaryUrl}
            size={200}
            level="M"
            includeMargin={false}
          />
        </div>

        {/* URL Box */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#161b28',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '10px',
          padding: '0.65rem 1rem',
          marginBottom: '1.25rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
            <Wifi size={16} color="#34d399" />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', color: '#f8fafc', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
              {primaryUrl}
            </span>
          </div>

          <button
            className="btn-secondary"
            style={{ fontSize: '0.78rem', padding: '0.35rem 0.75rem', marginLeft: '8px' }}
            onClick={handleCopy}
          >
            {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>

        {/* Notice */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          background: 'rgba(16, 185, 129, 0.08)',
          border: '1px solid rgba(16, 185, 129, 0.2)',
          borderRadius: '8px',
          padding: '0.75rem',
          fontSize: '0.78rem',
          color: '#a7f3d0',
          textAlign: 'left'
        }}>
          <ShieldCheck size={16} style={{ flexShrink: 0 }} />
          <span>
            Pairing grants this browser access to the library for seven days. Original photos remain in place and are not modified.
          </span>
        </div>
      </div>
    </div>
  );
}
