import { Row, Col, Card, Statistic } from 'antd';
import {
  HomeOutlined,
  DollarOutlined,
  BankOutlined,
  TagOutlined,
} from '@ant-design/icons';

export default function OverviewCards({ overview }) {
  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card>
          <Statistic
            title="房源总数"
            value={overview.total}
            prefix={<HomeOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="涉及小区"
            value={overview.communityCount}
            prefix={<BankOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="平均月租"
            value={overview.avgPrice}
            prefix={<DollarOutlined />}
            suffix="元"
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="平均单价"
            value={overview.avgUnitPrice}
            prefix={<TagOutlined />}
            suffix="元/㎡/月"
          />
        </Card>
      </Col>
    </Row>
  );
}
