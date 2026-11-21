import AnalyticsDashboard from "../hr/AnalyticsDashboard";
export const DirectorAnalytics = ({
  onExportReport,
}: {
  onExportReport: () => void;
}) => <AnalyticsDashboard onExportReport={onExportReport} />;
export default DirectorAnalytics;
