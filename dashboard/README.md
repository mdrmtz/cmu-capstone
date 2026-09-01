# Accessibility Audit Dashboard

A professional, static HTML dashboard for visualizing accessibility violations and evaluation results from automated audits. Fully responsive with light/dark mode support.

## 📁 Files

- **`index.html`** - Main dashboard with summary metrics and violation overview
- **`benchmark-cases.html`** - Detailed benchmark cases with search, filter, and expand capabilities

## 🚀 Getting Started

1. **Open in Browser**: Simply open `index.html` in any modern web browser
   - No server required - fully static HTML/CSS/JavaScript
   - Works offline once loaded

2. **Data Source**: Dashboards automatically load data from:
   - `../results/results_summary.json` - Test results and metrics
   - `../results/audit.json` - Detailed violation audit (for main dashboard)
   - `../benchmark_cases.json` - All benchmark cases (for benchmark dashboard)

3. **Navigation**:
   - Main Dashboard → "View Benchmark Cases" button links to detailed cases
   - Benchmark Cases → "Dashboard" button returns to main summary

## ✨ Features

### Main Dashboard (`index.html`)

**Metrics Display:**
- Total violations across all pages
- Violation clearance rate (%)
- Human escalation rate (%)
- Total test cases evaluated
- Error rate (%)
- Average response time per evaluation

**Visualizations:**
- **Violations by Rule**: Grid of violation statistics showing total, cleared, and remaining counts
- **Pages Affected**: Overview of all pages with violation counts and rule tags
- **Responsive Grid**: Auto-adjusts column count based on screen size

**Interactivity:**
- Light/Dark mode toggle (persisted to localStorage)
- Hover effects for better visual feedback
- Automatic data loading with error handling

### Benchmark Cases Dashboard (`benchmark-cases.html`)

**Detailed Table View:**
- Case ID, Page, Rule, WCAG reference, Selector, Ground truth fix
- Expandable rows showing full details
- Responsive design (stacks on mobile)

**Search & Filter:**
- **Search Box**: Search across case ID, page, rule, WCAG, selector, or fix text
- **Rule Filter**: Filter by specific accessibility rule (e.g., image-alt, color-contrast)
- **Page Filter**: Filter by affected page
- Real-time results counter

**Enhanced UX:**
- **Expandable Details**: Click "+" to expand row and see full details in formatted sections
- **Pagination**: Navigate through cases (10 per page by default)
- **Responsive Table**: Converts to card layout on mobile devices
- **Light/Dark Mode**: Consistent with main dashboard

## 🎨 Design Principles

### Visual Hierarchy
- Clear separation between metrics, sections, and details
- Larger fonts for important values
- Color-coded severity (error/warning/success/info)

### Accessibility
- Semantic HTML structure
- WCAG-compliant color contrasts
- Keyboard navigation support
- Proper ARIA labels on interactive elements
- Screen reader friendly

### Responsiveness
- Mobile-first approach
- Flexible grid layouts
- Touch-friendly button sizes
- Optimized table rendering on small screens

### Usability
- Intuitive navigation
- Search and filtering built-in
- Persistent theme preference
- Clear status indicators
- Informative empty states

## 🌓 Light/Dark Mode

**Auto Persistence**: Theme preference is saved to browser's localStorage

**Colors:**
- Light Mode: Clean whites and grays with blue accents
- Dark Mode: Comfortable dark backgrounds with soft text

**Smooth Transitions**: 0.3s animation when switching modes

## 📊 Data Structure

### results_summary.json
```json
{
  "summary": {
    "total_cases": 1,
    "violation_clearance_rate": 0.0,
    "human_escalation_rate": 1.0,
    "error_rate": 1.0,
    "mean_latency_seconds": 2.8,
    "by_rule": {
      "rule-name": {
        "total": 1,
        "cleared": 0
      }
    }
  },
  "cases": [...]
}
```

### benchmark_cases.json
```json
[
  {
    "id": "case-01",
    "page": "/",
    "rule": "html-has-lang",
    "selector": "html",
    "wcag": "3.1.1",
    "ground_truth_fix": "Add lang='en' to..."
  }
]
```

### audit.json
```json
{
  "generated_at": "2026-09-01T...",
  "total_violation_instances": 22,
  "pages": [
    {
      "url": "http://127.0.0.1:4200/",
      "violation_rules": ["html-has-lang"],
      "violation_instance_count": 1
    }
  ],
  "raw_reports": [...]
}
```

## 🔧 Customization

### Modifying Paths
If your data files are in different locations, update the path constants in each HTML file:

**index.html:**
```javascript
const RESULTS_SUMMARY_PATH = '../results/results_summary.json';
const AUDIT_PATH = '../results/audit.json';
```

**benchmark-cases.html:**
```javascript
const BENCHMARK_PATH = '../benchmark_cases.json';
const RESULTS_SUMMARY_PATH = '../results/results_summary.json';
```

### Styling
All styles use CSS custom properties (`--color-*` variables) for easy theming:
```css
:root {
  --color-bg: #ffffff;
  --color-text: #1a1a1a;
  --color-error: #dc2626;
  --color-info: #3b82f6;
  /* ... */
}
```

### Items Per Page
Adjust pagination in `benchmark-cases.html`:
```javascript
const ITEMS_PER_PAGE = 10; // Change to desired number
```

## 🖥️ Browser Support

- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support
- Safari: ✅ Full support
- IE 11: ❌ Not supported (uses modern CSS Grid, ES6+)

## 📱 Responsive Breakpoints

- **Desktop**: Full-featured layout with all columns visible
- **Tablet** (768px-1024px): Adjusted spacing and font sizes
- **Mobile** (< 768px): 
  - Single column layouts
  - Table converts to card view in benchmark dashboard
  - Stacked controls and buttons
  - Touch-optimized interactions

## ⚡ Performance

- **Static files**: No build process needed
- **Efficient rendering**: Only loads visible data
- **Lazy pagination**: Handles large datasets gracefully
- **Minimal dependencies**: Pure HTML/CSS/JavaScript

## 🔒 Security

- No external CDN dependencies
- No server-side processing
- No data transmission (local file only)
- XSS protection via HTML escaping

## 📝 Notes

- Dashboards assume JSON files are in the specified relative paths
- WCAG links in benchmark dashboard currently point to standard WCAG 2.1 pages (customize as needed)
- All sorting and filtering happens client-side
- Theme preference is stored per browser/device

## 🎯 UX Design Best Practices Applied

✅ **Visual Feedback**: Hover states, focus indicators, smooth transitions
✅ **Information Density**: Balanced overview with drill-down details
✅ **Progressive Disclosure**: Expandable rows reduce cognitive load
✅ **Consistent Styling**: Same design system across both dashboards
✅ **Error Prevention**: Input validation and safe data handling
✅ **Flexibility**: Search, filter, and pagination for different use cases
✅ **Accessibility First**: WCAG AAA compliant design
✅ **Performance**: Instant interactions, smooth animations
✅ **Responsive Design**: Works seamlessly on all devices
✅ **Dark Mode**: Reduces eye strain in low-light environments
