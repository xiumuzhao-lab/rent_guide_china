import { Alert, Card, Row, Col } from 'antd';

export default function AnalysisReport({ summary, suggestions }) {
  if (!summary) return null;

  return (
    <div style={{ background: '#fff', borderRadius: 8, overflow: 'hidden' }}>
      <div style={{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        padding: '16px 20px',
      }}>
        <div style={{ color: '#fff', fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
          AI 租房分析报告
        </div>
        <div style={{ color: 'rgba(255,255,255,0.9)', fontSize: 13, lineHeight: 1.7 }}>
          {summary}
        </div>
      </div>
      <div style={{ padding: '12px 16px' }}>
        <Row gutter={[12, 10]}>
          {suggestions.map((s, i) => (
            <Col key={i} xs={24} sm={12}>
              <div style={{
                background: '#f8f9fa',
                borderRadius: 6,
                padding: '10px 14px',
                height: '100%',
              }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                  {s.icon} {s.title}
                </div>
                <div style={{ fontSize: 12, color: '#555', lineHeight: 1.6 }}>
                  {s.text}
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  );
}
