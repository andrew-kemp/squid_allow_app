import { useNavigate } from 'react-router-dom';

export default function GearIconButton() {
  const navigate = useNavigate();
  return (
    <button
      title="Admin Panel"
      style={{
        position: 'absolute',
        top: 24,
        right: 32,
        background: 'none',
        border: 'none',
        cursor: 'pointer'
      }}
      onClick={() => navigate('/admin')}
    >
      {/* Simple SVG gear icon */}
      <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
        <path d="M12 15.5A3.5 3.5 0 1 0 12 8.5a3.5 3.5 0 0 0 0 7Zm7.43-2.91c.04-.32.07-.65.07-.99s-.03-.67-.07-.99l2.11-1.65a.5.5 0 0 0 .12-.64l-2-3.46a.5.5 0 0 0-.61-.22l-2.49 1a7.03 7.03 0 0 0-1.7-.99l-.38-2.65A.5.5 0 0 0 12 2h-4a.5.5 0 0 0-.5.42l-.38 2.65c-.6.23-1.17.53-1.7.99l-2.49-1a.5.5 0 0 0-.61.22l-2 3.46a.5.5 0 0 0 .12.64l2.11 1.65c-.04.32-.07.65-.07.99s.03.67.07.99l-2.11 1.65a.5.5 0 0 0-.12.64l2 3.46a.5.5 0 0 0 .61.22l2.49-1c.52.46 1.09.76 1.7.99l.38 2.65A.5.5 0 0 0 8 22h4a.5.5 0 0 0 .5-.42l.38-2.65c.6-.23 1.17-.53 1.7-.99l2.49 1a.5.5 0 0 0 .61-.22l2-3.46a.5.5 0 0 0-.12-.64l-2.11-1.65Z" fill="#2D3A7B"/>
      </svg>
    </button>
  );
}
