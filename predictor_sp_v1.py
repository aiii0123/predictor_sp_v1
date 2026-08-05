"""
巡夢事件預測系統 - 手機優化版（無子事件）
簡化操作：點擊即記錄，適合手機使用
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from collections import defaultdict, Counter
import re
import os

# ============ 頁面設定 ============
st.set_page_config(
    page_title="巡夢事件預測系統",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 顏色定義 ============
COLORS = ['綠', '藍', '紫', '金', '灰']
COLOR_EMOJI = {'綠': '🟢', '藍': '🔵', '紫': '🟣', '金': '🟡', '灰': '⚪', '中斷': '⏸️'}
COLOR_HEX = {
    '綠': '#2ecc71',
    '藍': '#3498db',
    '紫': '#9b59b6',
    '金': '#d4a017',
    '灰': '#95a5a6',
    '中斷': '#555555'
}


# ============ 資料庫類別 ============
class Database:
    def __init__(self, db_name="xunmeng.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                event_type TEXT NOT NULL,
                event_subtype TEXT,
                sequence_number INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                predicted_type TEXT NOT NULL,
                actual_type TEXT NOT NULL,
                confidence REAL,
                was_correct INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_weights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                model_name TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                accuracy REAL DEFAULT 0.0,
                sample_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_id, model_name)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS rule_accuracy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                rule_name TEXT NOT NULL,
                hits INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                accuracy REAL DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_id, rule_name)
            )
        ''')
        self.conn.commit()
    
    def add_account(self, name):
        try:
            self.cursor.execute("INSERT INTO accounts (name) VALUES (?)", (name,))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
    
    def get_accounts(self):
        self.cursor.execute("SELECT id, name FROM accounts ORDER BY id")
        return self.cursor.fetchall()
    
    def get_account_id(self, name):
        self.cursor.execute("SELECT id FROM accounts WHERE name = ?", (name,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def add_event(self, account_id, event_type, event_subtype=""):
        self.cursor.execute(
            "SELECT MAX(sequence_number) FROM events WHERE account_id = ?",
            (account_id,)
        )
        max_seq = self.cursor.fetchone()[0]
        seq = (max_seq + 1) if max_seq else 1
        
        self.cursor.execute('''
            INSERT INTO events (account_id, event_type, event_subtype, sequence_number)
            VALUES (?, ?, ?, ?)
        ''', (account_id, event_type, event_subtype, seq))
        self.conn.commit()
        return seq
    
    def get_events(self, account_id, limit=None):
        query = '''
            SELECT sequence_number, event_type, event_subtype, recorded_at
            FROM events
            WHERE account_id = ?
            ORDER BY sequence_number DESC
        '''
        if limit:
            query += f" LIMIT {limit}"
        self.cursor.execute(query, (account_id,))
        return self.cursor.fetchall()
    
    def get_all_events_ordered(self, account_id):
        self.cursor.execute('''
            SELECT sequence_number, event_type, event_subtype
            FROM events
            WHERE account_id = ?
            ORDER BY sequence_number ASC
        ''', (account_id,))
        return self.cursor.fetchall()
    
    def delete_account(self, account_id):
        self.cursor.execute("DELETE FROM events WHERE account_id = ?", (account_id,))
        self.cursor.execute("DELETE FROM feedback WHERE account_id = ?", (account_id,))
        self.cursor.execute("DELETE FROM model_weights WHERE account_id = ?", (account_id,))
        self.cursor.execute("DELETE FROM rule_accuracy WHERE account_id = ?", (account_id,))
        self.cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self.conn.commit()
    
    def delete_last_event(self, account_id):
        self.cursor.execute('''
            DELETE FROM feedback
            WHERE id = (
                SELECT id FROM feedback
                WHERE account_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            )
        ''', (account_id,))
        
        self.cursor.execute('''
            DELETE FROM events
            WHERE id = (
                SELECT id FROM events
                WHERE account_id = ?
                ORDER BY sequence_number DESC
                LIMIT 1
            )
        ''', (account_id,))
        self.conn.commit()
    
    def import_from_excel(self, account_id, df):
        events = []
        for _, row in df.iterrows():
            if pd.notna(row[0]):
                event_str = str(row[0]).strip()
                if event_str and event_str != 'nan':
                    if '金' in event_str:
                        event_type = '金'
                        subtype = re.sub(r'^金\(|\)$', '', event_str).strip()
                    elif '藍' in event_str:
                        event_type = '藍'
                        subtype = re.sub(r'^藍\(|\)$', '', event_str).strip()
                    elif '紫' in event_str:
                        event_type = '紫'
                        subtype = re.sub(r'^紫\(|\)$', '', event_str).strip()
                    elif '綠' in event_str:
                        event_type = '綠'
                        subtype = ''
                    elif '灰' in event_str or '失敗' in event_str:
                        event_type = '灰'
                        subtype = ''
                    else:
                        continue
                    events.append((event_type, subtype))
        
        self.cursor.execute(
            "SELECT MAX(sequence_number) FROM events WHERE account_id = ?",
            (account_id,)
        )
        max_seq = self.cursor.fetchone()[0] or 0
        
        for i, (event_type, subtype) in enumerate(events, 1):
            seq = max_seq + i
            self.cursor.execute('''
                INSERT INTO events (account_id, event_type, event_subtype, sequence_number)
                VALUES (?, ?, ?, ?)
            ''', (account_id, event_type, subtype, seq))
        self.conn.commit()
        return len(events)
    
    def add_feedback(self, account_id, predicted_type, actual_type, confidence):
        was_correct = 1 if predicted_type == actual_type else 0
        self.cursor.execute('''
            INSERT INTO feedback (account_id, predicted_type, actual_type, confidence, was_correct)
            VALUES (?, ?, ?, ?, ?)
        ''', (account_id, predicted_type, actual_type, confidence, was_correct))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_feedback_stats(self, account_id):
        self.cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(was_correct) as correct,
                AVG(was_correct) as accuracy,
                AVG(confidence) as avg_confidence
            FROM feedback
            WHERE account_id = ?
        ''', (account_id,))
        result = self.cursor.fetchone()
        
        if result and result[0] > 0:
            return {
                'total': result[0],
                'correct': result[1],
                'accuracy': result[2],
                'avg_confidence': result[3]
            }
        return None
    
    def update_model_weight(self, account_id, model_name, accuracy):
        self.cursor.execute('''
            SELECT weight, sample_count FROM model_weights
            WHERE account_id = ? AND model_name = ?
        ''', (account_id, model_name))
        result = self.cursor.fetchone()
        
        if result:
            old_weight, count = result
            new_count = count + 1
            new_weight = old_weight * 0.7 + (accuracy * 1.5 + 0.3) * 0.3
            new_weight = max(0.1, min(2.0, new_weight))
            
            self.cursor.execute('''
                UPDATE model_weights
                SET weight = ?, accuracy = ?, sample_count = ?, updated_at = CURRENT_TIMESTAMP
                WHERE account_id = ? AND model_name = ?
            ''', (new_weight, accuracy, new_count, account_id, model_name))
        else:
            weight = max(0.1, min(2.0, accuracy * 2 + 0.3))
            self.cursor.execute('''
                INSERT INTO model_weights (account_id, model_name, weight, accuracy, sample_count)
                VALUES (?, ?, ?, ?, 1)
            ''', (account_id, model_name, weight, accuracy))
        
        self.conn.commit()
    
    def get_all_model_weights(self, account_id):
        self.cursor.execute('''
            SELECT model_name, weight, accuracy, sample_count
            FROM model_weights
            WHERE account_id = ?
            ORDER BY weight DESC
        ''', (account_id,))
        return self.cursor.fetchall()
    
    def update_rule_accuracy(self, account_id, rule_name, was_correct):
        self.cursor.execute('''
            SELECT hits, total FROM rule_accuracy
            WHERE account_id = ? AND rule_name = ?
        ''', (account_id, rule_name))
        result = self.cursor.fetchone()
        
        if result:
            hits, total = result
            new_hits = hits + (1 if was_correct else 0)
            new_total = total + 1
            new_accuracy = new_hits / new_total if new_total > 0 else 0
            
            self.cursor.execute('''
                UPDATE rule_accuracy
                SET hits = ?, total = ?, accuracy = ?, updated_at = CURRENT_TIMESTAMP
                WHERE account_id = ? AND rule_name = ?
            ''', (new_hits, new_total, new_accuracy, account_id, rule_name))
        else:
            hits = 1 if was_correct else 0
            total = 1
            accuracy = 1.0 if was_correct else 0.0
            
            self.cursor.execute('''
                INSERT INTO rule_accuracy (account_id, rule_name, hits, total, accuracy)
                VALUES (?, ?, ?, ?, ?)
            ''', (account_id, rule_name, hits, total, accuracy))
        
        self.conn.commit()
    
    def get_rule_accuracies(self, account_id):
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rule_accuracy'")
        if not self.cursor.fetchone():
            return []
        
        self.cursor.execute('''
            SELECT rule_name, hits, total, accuracy
            FROM rule_accuracy
            WHERE account_id = ?
            ORDER BY accuracy DESC
        ''', (account_id,))
        return self.cursor.fetchall()
    
    def close(self):
        self.conn.close()


# ============ 預測引擎 ============
class MarkovChain:
    def __init__(self, colors):
        self.colors = colors
        self.transitions = {}
        self.build_transitions()
    
    def build_transitions(self):
        for order in [1, 2, 3]:
            self.transitions[order] = defaultdict(Counter)
            for i in range(len(self.colors) - order):
                state = tuple(self.colors[i:i+order])
                next_state = self.colors[i+order]
                self.transitions[order][state][next_state] += 1
    
    def predict(self, history, order=3):
        if len(history) < order:
            for o in range(order-1, 0, -1):
                if len(history) >= o:
                    return self.predict(history, o)
            return None
        
        state = tuple(history[-order:])
        if state in self.transitions[order]:
            counter = self.transitions[order][state]
            total = sum(counter.values())
            return {k: v/total for k, v in counter.items()}
        else:
            if order > 1:
                return self.predict(history, order-1)
            return None


class GapAnalyzer:
    def __init__(self, colors):
        self.colors = colors
    
    def get_current_gap(self, color):
        for i in range(len(self.colors)-1, -1, -1):
            if self.colors[i] == color:
                return len(self.colors) - i - 1
        return len(self.colors)
    
    def get_gap_probability(self, color):
        current_gap = self.get_current_gap(color)
        
        if color == '金':
            if current_gap >= 8:
                return min(0.3 + (current_gap - 8) * 0.08, 0.9)
            else:
                return 0.05 + current_gap * 0.03
        elif color == '藍':
            if current_gap >= 6:
                return min(0.25 + (current_gap - 6) * 0.07, 0.85)
            else:
                return 0.08 + current_gap * 0.03
        else:
            return 0.1 + current_gap * 0.02


class SimilarSequenceSearch:
    def __init__(self, colors):
        self.colors = colors
    
    def get_similar_prediction(self, history):
        if len(history) < 2 or len(self.colors) < 5:
            return None
        
        pattern_len = min(4, len(history))
        pattern = history[-pattern_len:]
        
        votes = Counter()
        total_weight = 0
        
        for i in range(len(self.colors) - pattern_len - 1):
            segment = self.colors[i:i+pattern_len]
            next_event = self.colors[i+pattern_len]
            
            matches = sum(1 for a, b in zip(pattern, segment) if a == b)
            similarity = matches / pattern_len
            
            if similarity >= 0.5:
                weight = similarity ** 2
                votes[next_event] += weight
                total_weight += weight
        
        if total_weight == 0:
            return None
        
        return {k: v/total_weight for k, v in votes.items()}


class RuleEngine:
    def __init__(self, colors, account_id, db):
        self.colors = colors
        self.account_id = account_id
        self.db = db
        self.rule_accuracies = self._load_rule_accuracies()
    
    def _load_rule_accuracies(self):
        accuracies = {}
        if self.account_id:
            try:
                results = self.db.get_rule_accuracies(self.account_id)
                for name, hits, total, acc in results:
                    accuracies[name] = acc
            except Exception as e:
                pass
        return accuracies
    
    def _get_rule_weight(self, rule_name, base_weight):
        accuracy = self.rule_accuracies.get(rule_name, 0.5)
        return base_weight * (0.5 + 0.5 * accuracy)
    
    def predict(self, history):
        results = []
        
        if len(history) >= 6:
            last_blue = -1
            for i in range(len(history)-1, -1, -1):
                if history[i] == '藍':
                    last_blue = i
                    break
            gap = len(history) - last_blue - 1 if last_blue != -1 else len(history)
            if gap >= 6:
                weight = self._get_rule_weight('久沒藍出藍或紫', 1.2)
                results.append({
                    'name': '久沒藍出藍或紫',
                    'prediction': {'藍': 0.45, '紫': 0.25, '金': 0.18, '綠': 0.10, '灰': 0.02},
                    'weight': weight
                })
        
        if len(history) >= 1 and history[-1] == '灰':
            weight = self._get_rule_weight('灰後出紫或藍', 1.0)
            results.append({
                'name': '灰後出紫或藍',
                'prediction': {'紫': 0.35, '藍': 0.30, '金': 0.20, '綠': 0.13, '灰': 0.02},
                'weight': weight
            })
        
        if len(history) >= 2 and history[-1] == '藍' and history[-2] == '藍':
            weight = self._get_rule_weight('藍藍後出金', 1.1)
            results.append({
                'name': '藍藍後出金',
                'prediction': {'金': 0.40, '紫': 0.25, '藍': 0.20, '綠': 0.13, '灰': 0.02},
                'weight': weight
            })
        
        if len(history) >= 3:
            streak = 0
            for i in range(len(history)-1, -1, -1):
                if history[i] == '綠':
                    streak += 1
                else:
                    break
            if streak >= 3:
                weight = self._get_rule_weight('連綠後出藍', 0.8)
                results.append({
                    'name': '連綠後出藍',
                    'prediction': {'藍': 0.33, '紫': 0.27, '金': 0.20, '綠': 0.18, '灰': 0.02},
                    'weight': weight
                })
        
        if len(history) >= 1:
            recent_events = history[-8:] if len(history) >= 8 else history
            if '金' in recent_events:
                gold_pos = len(recent_events) - 1 - recent_events[::-1].index('金')
                if gold_pos <= 5:
                    weight = self._get_rule_weight('金後CD', 0.9)
                    results.append({
                        'name': '金後CD',
                        'prediction': {'金': 0.05, '藍': 0.25, '紫': 0.25, '綠': 0.40, '灰': 0.05},
                        'weight': weight
                    })
        
        return results


class AdaptivePredictor:
    def __init__(self, events, account_id, db):
        self.colors = [e[1] for e in events if e[1] != '中斷']
        self.account_id = account_id
        self.db = db
        
        self.markov = MarkovChain(self.colors)
        self.gap_analyzer = GapAnalyzer(self.colors)
        self.similar_search = SimilarSequenceSearch(self.colors)
        self.rule_engine = RuleEngine(self.colors, account_id, db)
        
        self.model_weights = self._load_weights()
    
    def _load_weights(self):
        default_weights = {'markov': 0.30, 'gap': 0.20, 'similar': 0.25, 'rule': 0.25}
        
        if self.account_id:
            try:
                results = self.db.get_all_model_weights(self.account_id)
                for name, weight, accuracy, count in results:
                    if name == 'Markov Chain':
                        default_weights['markov'] = weight
                    elif name == '間隔分析':
                        default_weights['gap'] = weight
                    elif name == '相似序列搜尋':
                        default_weights['similar'] = weight
                    elif name == '規則引擎':
                        default_weights['rule'] = weight
            except Exception as e:
                pass
        
        return default_weights
    
    def _get_adaptive_weight(self, model_name, base_weight):
        feedback_stats = self.db.get_feedback_stats(self.account_id)
        
        if feedback_stats and feedback_stats['total'] > 5:
            accuracy = feedback_stats['accuracy']
            adjustment = (accuracy - 0.5) * 0.4
            return max(0.05, min(0.6, base_weight + adjustment))
        else:
            return base_weight
    
    def predict(self):
        if len(self.colors) < 3:
            return {
                'probabilities': {'綠': 40, '藍': 20, '紫': 20, '金': 15, '灰': 5},
                'most_likely': '綠',
                'confidence': 0.4,
                'suggestions': ['📊 資料不足（少於3筆），建議繼續記錄'],
                'since_last_gold': 0,
                'since_last_blue': 0,
                'details': []
            }
        
        history = self.colors
        scores = {color: 0 for color in COLORS}
        details = []
        
        markov_weight = self._get_adaptive_weight('markov', self.model_weights['markov'])
        markov_pred = self.markov.predict(history, order=3)
        if markov_pred:
            for color, prob in markov_pred.items():
                scores[color] += prob * markov_weight
            details.append(('Markov Chain (3階)', markov_pred, markov_weight))
        else:
            markov_pred = self.markov.predict(history, order=2)
            if markov_pred:
                for color, prob in markov_pred.items():
                    scores[color] += prob * markov_weight * 0.85
                details.append(('Markov Chain (2階)', markov_pred, markov_weight * 0.85))
        
        gap_weight = self._get_adaptive_weight('gap', self.model_weights['gap'])
        gap_scores = {}
        for color in COLORS:
            gap_scores[color] = self.gap_analyzer.get_gap_probability(color)
        total_gap = sum(gap_scores.values())
        if total_gap > 0:
            normalized_gap = {k: v/total_gap for k, v in gap_scores.items()}
            for color in COLORS:
                scores[color] += normalized_gap[color] * gap_weight
            details.append(('間隔分析（保底偵測）', normalized_gap, gap_weight))
        
        similar_weight = self._get_adaptive_weight('similar', self.model_weights['similar'])
        similar_pred = self.similar_search.get_similar_prediction(history)
        if similar_pred:
            for color, prob in similar_pred.items():
                scores[color] += prob * similar_weight
            details.append(('相似序列搜尋', similar_pred, similar_weight))
        
        rule_weight = self._get_adaptive_weight('rule', self.model_weights['rule'])
        rule_results = self.rule_engine.predict(history)
        if rule_results:
            rule_scores = {color: 0 for color in COLORS}
            total_rule_weight = 0
            for result in rule_results:
                pred = result['prediction']
                weight = result['weight']
                total_rule_weight += weight
                for color, prob in pred.items():
                    rule_scores[color] += prob * weight
            
            if total_rule_weight > 0:
                for color in COLORS:
                    rule_scores[color] /= total_rule_weight
                    scores[color] += rule_scores[color] * rule_weight
                details.append(('規則引擎（經驗規則）', rule_scores, rule_weight))
        
        total_score = sum(scores.values())
        if total_score > 0:
            for color in COLORS:
                scores[color] = (scores[color] / total_score) * 100
        
        most_likely = max(scores, key=scores.get)
        confidence = scores[most_likely] / 100
        
        suggestions = self._generate_suggestions(scores, history)
        
        feedback_stats = self.db.get_feedback_stats(self.account_id)
        if feedback_stats and feedback_stats['total'] > 0:
            suggestions.append(f"🧠 已學習 {feedback_stats['total']} 次，準確率 {feedback_stats['accuracy']*100:.1f}%")
        else:
            suggestions.append("💡 記錄事件時系統會自動學習")
        
        return {
            'probabilities': scores,
            'most_likely': most_likely,
            'confidence': confidence,
            'suggestions': suggestions,
            'since_last_gold': self.gap_analyzer.get_current_gap('金'),
            'since_last_blue': self.gap_analyzer.get_current_gap('藍'),
            'details': details,
            'feedback_stats': feedback_stats
        }
    
    def _generate_suggestions(self, scores, history):
        suggestions = []
        
        gold_gap = self.gap_analyzer.get_current_gap('金')
        blue_gap = self.gap_analyzer.get_current_gap('藍')
        
        if gold_gap >= 8:
            suggestions.append(f"⚠️ 已 {gold_gap} 次沒金，強烈建議出手！（金機率 {scores['金']:.1f}%）")
        elif gold_gap >= 5:
            suggestions.append(f"💡 已 {gold_gap} 次沒金，可以考慮出手（金機率 {scores['金']:.1f}%）")
        
        if blue_gap >= 6:
            suggestions.append(f"🔵 已 {blue_gap} 次沒藍，藍色即將出現！（藍機率 {scores['藍']:.1f}%）")
        elif blue_gap >= 4:
            suggestions.append(f"💡 已 {blue_gap} 次沒藍，藍色接近保底（藍機率 {scores['藍']:.1f}%）")
        
        if max(scores.values()) > 60:
            suggestions.append(f"🎯 高信心度預測：{max(scores, key=scores.get)}（{max(scores.values()):.1f}%）")
        
        if len(history) >= 2 and history[-1] == '藍' and history[-2] == '藍':
            suggestions.append("🔵🔵 檢測到藍藍連發模式，金可能即將出現！")
        
        if len(history) >= 1 and history[-1] == '灰':
            suggestions.append("⚪ 剛出灰，接下來紫或藍機率高！")
        
        green_streak = 0
        for i in range(len(history)-1, -1, -1):
            if history[i] == '綠':
                green_streak += 1
            else:
                break
        if green_streak >= 3:
            suggestions.append(f"🟢 已連續 {green_streak} 綠，可能即將出藍或紫！")
        
        if not suggestions:
            suggestions.append("📊 目前處於平穩期，建議持續記錄")
        
        return suggestions


# ============ 自訂 CSS（手機優化 + 清楚建議） ============
def apply_custom_css():
    st.markdown("""
    <style>
    /* ===== 手機優化 ===== */
    @media (max-width: 768px) {
        .stButton button {
            font-size: 1.3rem !important;
            padding: 1rem 0.3rem !important;
            min-height: 4rem !important;
            border-radius: 12px !important;
        }
        .stSelectbox {
            font-size: 1.1rem !important;
        }
        .stProgress > div > div {
            height: 1.5rem !important;
        }
        .stMetric {
            font-size: 1.1rem !important;
        }
    }
    
    /* ===== 標題 ===== */
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(135deg, #f1c40f, #e67e22);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
    }
    .sub-header {
        text-align: center;
        color: #95a5a6;
        margin-bottom: 1.2rem;
        font-size: 0.85rem;
    }
    
    /* ===== 預測框 ===== */
    .prediction-box {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border-radius: 15px;
        padding: 20px;
        border: 1px solid #f1c40f44;
        text-align: center;
        margin: 10px 0;
    }
    
    /* ===== 建議框（清楚版） ===== */
    .suggestion-box {
        background: #2a2a4a;
        border-radius: 10px;
        padding: 14px 18px;
        border-left: 5px solid #f1c40f;
        margin: 8px 0;
        font-size: 1rem;
        color: #f0f0f0 !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        line-height: 1.6;
    }
    .suggestion-box * {
        color: #f0f0f0 !important;
    }
    
    /* ===== 機率條文字 ===== */
    .stMarkdown div[style*="display: flex"] span {
        color: #e0e0e0 !important;
        font-weight: 500;
    }
    
    /* ===== 側邊欄 ===== */
    .css-1d391kg, .css-1adrfps {
        background-color: #0e1117;
    }
    
    /* ===== 按鈕懸停效果 ===== */
    .stButton button:hover {
        transform: scale(1.02);
        transition: 0.2s;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    
    /* ===== 統計數字 ===== */
    .stMetric .css-1xarl3l {
        font-size: 1.8rem !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ============ 主程式 ============
def main():
    apply_custom_css()
    
    st.markdown('<div class="main-header">🔮 巡夢事件預測系統</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">📱 手機優化 · 點擊即記錄 · 自動學習</div>', unsafe_allow_html=True)
    
    # 初始化 Session State
    if 'db' not in st.session_state:
        st.session_state.db = Database()
    if 'last_prediction' not in st.session_state:
        st.session_state.last_prediction = None
    if 'last_confidence' not in st.session_state:
        st.session_state.last_confidence = None
    
    # ===== 側邊欄 =====
    with st.sidebar:
        st.header("📁 帳號管理")
        
        accounts = st.session_state.db.get_accounts()
        account_names = [name for _, name in accounts]
        
        if account_names:
            selected_account = st.selectbox("選擇帳號", account_names, key="account_select")
            account_id = st.session_state.db.get_account_id(selected_account)
            
            events = st.session_state.db.get_all_events_ordered(account_id)
            colors = [e[1] for e in events if e[1] != '中斷']
            if colors:
                st.caption(f"📊 共 {len(colors)} 筆記錄")
        else:
            st.info("尚無帳號，請建立一個")
            selected_account = None
            account_id = None
        
        st.divider()
        
        st.subheader("➕ 新增帳號")
        new_account = st.text_input("帳號名稱", placeholder="例如：帳號1")
        if st.button("建立帳號", use_container_width=True):
            if new_account:
                result = st.session_state.db.add_account(new_account)
                if result:
                    st.success(f"✅ 帳號「{new_account}」已建立")
                    st.rerun()
                else:
                    st.error("❌ 帳號已存在")
            else:
                st.warning("請輸入帳號名稱")
        
        if account_id:
            if st.button("🗑️ 刪除此帳號", use_container_width=True):
                st.session_state.db.delete_account(account_id)
                st.success("帳號已刪除")
                st.rerun()
        
        st.divider()
        
        st.subheader("📤 匯入Excel")
        uploaded_file = st.file_uploader(
            "選擇Excel檔案",
            type=['xlsx', 'xls'],
            help="第一欄為事件名稱"
        )
        if uploaded_file and account_id:
            if st.button("匯入資料", use_container_width=True):
                try:
                    df = pd.read_excel(uploaded_file, header=None)
                    count = st.session_state.db.import_from_excel(account_id, df)
                    st.success(f"✅ 已匯入 {count} 筆事件")
                    st.rerun()
                except Exception as e:
                    st.error(f"匯入失敗：{e}")
        
        st.divider()
        
        if st.button("🔧 修復資料庫", use_container_width=True):
            try:
                st.session_state.db.create_tables()
                st.success("✅ 資料庫已修復")
                st.rerun()
            except Exception as e:
                st.error(f"修復失敗：{e}")
        
        st.divider()
        
        with st.expander("📖 使用說明"):
            st.markdown("""
            **點擊即記錄：**
            - 🟢 綠 → 直接記錄
            - 🔵 藍 → 直接記錄
            - 🟣 紫 → 直接記錄
            - 🟡 金 → 直接記錄
            - ⚪ 灰 → 直接記錄
            - ⏸️ 中斷 → 標記時間斷點
            
            **預測機制：**
            - Markov Chain（1-3階）
            - 間隔分析（保底偵測）
            - 相似序列搜尋
            - 規則引擎（5條經驗規則）
            """)
    
    # ===== 主要內容 =====
    if account_id:
        events = st.session_state.db.get_all_events_ordered(account_id)
        colors_only = [e[1] for e in events if e[1] != '中斷']
        
        # ===== 事件記錄 =====
        st.subheader("📝 點擊記錄事件")
        
        # 2行 x 3列 大按鈕（適合手機）
        row1 = st.columns(3)
        row2 = st.columns(3)
        
        buttons = [
            (row1[0], '🟢 綠', '綠', '#2ecc71'),
            (row1[1], '🔵 藍', '藍', '#3498db'),
            (row1[2], '🟣 紫', '紫', '#9b59b6'),
            (row2[0], '🟡 金', '金', '#d4a017'),
            (row2[1], '⚪ 灰', '灰', '#95a5a6'),
            (row2[2], '⏸️ 中斷', '中斷', '#555555'),
        ]
        
        for col, label, key, color in buttons:
            if col.button(label, use_container_width=True, key=f"btn_{key}"):
                if key == '中斷':
                    st.session_state.db.add_event(account_id, '中斷', '')
                    st.success("⏸️ 已標記中斷點")
                    st.rerun()
                else:
                    st.session_state.db.add_event(account_id, key, '')
                    # 自動回饋
                    if st.session_state.last_prediction:
                        st.session_state.db.add_feedback(
                            account_id, 
                            st.session_state.last_prediction, 
                            key, 
                            st.session_state.last_confidence or 0.5
                        )
                    st.success(f"✅ 已記錄：{key}")
                    st.rerun()
        
        st.divider()
        
        # ===== 預測結果 =====
        col_pred_left, col_pred_right = st.columns([1, 1])
        
        with col_pred_left:
            st.subheader("🔮 預測結果")
            
            if len(colors_only) >= 3:
                predictor = AdaptivePredictor(events, account_id, st.session_state.db)
                result = predictor.predict()
                
                st.session_state.last_prediction = result['most_likely']
                st.session_state.last_confidence = result['confidence']
                
                most = result['most_likely']
                emoji = COLOR_EMOJI.get(most, '❓')
                color_hex = COLOR_HEX.get(most, '#ffffff')
                
                st.markdown(
                    f"""
                    <div class="prediction-box">
                        <div style="font-size: 0.85rem; color: #95a5a6;">⭐ 下一次最可能出現</div>
                        <div style="font-size: 3rem; font-weight: bold; color: {color_hex};">
                            {emoji} {most}
                        </div>
                        <div style="font-size: 0.85rem; color: #95a5a6;">
                            信心度：{result['confidence']*100:.1f}%
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                st.markdown("**各顏色機率：**")
                for color in COLORS:
                    prob = result['probabilities'].get(color, 0)
                    color_hex = COLOR_HEX.get(color, '#808080')
                    
                    st.markdown(
                        f"""
                        <div style="display: flex; align-items: center; margin: 4px 0;">
                            <span style="width: 50px; font-size: 1rem;">{COLOR_EMOJI[color]} {color}</span>
                            <div style="flex: 1; height: 24px; background: #2d2d2d; border-radius: 12px; overflow: hidden; margin: 0 10px;">
                                <div style="width: {prob}%; height: 100%; background: {color_hex}; border-radius: 12px; transition: width 0.5s;"></div>
                            </div>
                            <span style="width: 50px; text-align: right; font-weight: bold; color: #e0e0e0;">{prob:.1f}%</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            else:
                st.info("📊 記錄至少 3 筆事件後開始預測")
        
        with col_pred_right:
            st.subheader("💡 建議")
            if len(colors_only) >= 3:
                for suggestion in result.get('suggestions', []):
                    st.markdown(f'<div class="suggestion-box">{suggestion}</div>', unsafe_allow_html=True)
            else:
                st.info("📊 記錄更多事件後會顯示建議")
            
            st.subheader("📊 統計")
            
            if len(colors_only) >= 3:
                col_stat1, col_stat2 = st.columns(2)
                with col_stat1:
                    st.metric("🟡 金保底", f"{result['since_last_gold']} 次")
                with col_stat2:
                    st.metric("🔵 藍保底", f"{result['since_last_blue']} 次")
                
                feedback_stats = result.get('feedback_stats')
                if feedback_stats:
                    st.metric(
                        "🧠 學習狀態", 
                        f"{feedback_stats['total']}次",
                        f"準確率 {feedback_stats['accuracy']*100:.0f}%"
                    )
            else:
                st.caption("等待更多數據...")
        
        # ===== 歷史紀錄 =====
        st.divider()
        st.subheader("📜 歷史紀錄（最近20筆）")
        
        recent_events = st.session_state.db.get_events(account_id, limit=20)
        if recent_events:
            history_text = ""
            for seq, event_type, subtype, recorded_at in recent_events:
                time_str = recorded_at[:16] if recorded_at else ""
                emoji = COLOR_EMOJI.get(event_type, '')
                
                if event_type == '中斷':
                    history_text += f"━━━ ⏸️ 中斷點 ━━━  {time_str}\n"
                else:
                    history_text += f"{seq:3d}. {emoji} {event_type}  {time_str}\n"
            
            st.text(history_text)
        else:
            st.info("尚無記錄")
        
        if st.button("↩️ 撤回最後一筆"):
            st.session_state.db.delete_last_event(account_id)
            st.success("已撤回")
            st.rerun()
    
    else:
        st.info("👈 請在左側建立或選擇一個帳號開始使用")
        
        with st.expander("🚀 快速開始"):
            st.markdown("""
            ### 使用步驟：
            1. 在左側輸入帳號名稱，點擊「建立帳號」
            2. 選擇剛建立的帳號
            3. 點擊顏色按鈕記錄事件
            4. 右側會自動顯示預測結果
            5. 可以匯入 Excel 快速導入歷史資料
            
            ### 手機使用：
            - 將此網頁加入主畫面，就像 APP 一樣
            - 所有事件點擊即記錄，不需要選子類型
            """)
    
   


if __name__ == "__main__":
    main()
