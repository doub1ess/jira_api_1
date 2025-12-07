import unittest
from unittest.mock import patch, Mock
import sys
import os
from datetime import datetime
from collections import defaultdict

# Добавляем путь к коду
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from jira_analyzer import calculate_time, get_jira_issues, task_1, task_3, task_4

class TestJiraAnalytics(unittest.TestCase):
    
    def test_01_calculate_time_correct(self):
        """ТЕСТ 1: Расчет времени между датами (основа для гистограмм)"""
        created = "2023-01-01T10:00:00.000+0000"
        resolved = "2023-01-05T10:00:00.000+0000"
        result = calculate_time(created, resolved)
        self.assertEqual(result, 4)  # 4 дня разницы

    def test_02_calculate_time_same_day(self):
        """ТЕСТ 2: Расчет времени в один день (граничный случай)"""
        created = "2023-01-01T10:00:00.000+0000"
        resolved = "2023-01-01T20:00:00.000+0000"
        result = calculate_time(created, resolved)
        self.assertEqual(result, 0)  # 0 дней

    @patch('jira_analyzer.requests.get')
    def test_03_get_jira_issues_correct_jql(self, mock_get):
        """ТЕСТ 3: Правильный JQL запрос к JIRA (Closed+Resolved, проект KAFKA)"""
        mock_response = Mock()
        mock_response.json.return_value = {'issues': []}
        mock_get.return_value = mock_response
        
        get_jira_issues()
        
        # ПРОВЕРЯЕМ: вызван ли requests.get с ПРАВИЛЬНЫМИ параметрами?
        mock_get.assert_called_once()
        call_args = mock_get.call_args[1]  # params из requests.get(url, params=...)
        self.assertIn("jql", call_args['params'])
        self.assertIn("project=KAFKA AND status in (Closed, Resolved)", call_args['params']['jql'])
        self.assertEqual(call_args['params']['maxResults'], 100)

    @patch('jira_analyzer.requests.get')
    def test_04_task1_open_time_histogram_data(self, mock_get):
        """ТЕСТ 4: task_1() правильно собирает данные для гистограммы времени"""
        # Мокаем matplotlib чтобы не рисовал графики
        with patch('jira_analyzer.plt') as mock_plt:
            mock_response = Mock()
            mock_response.json.return_value = {
                'issues': [
                    {'fields': {'created': '2023-01-01T00:00:00.000+0000', 'resolutiondate': '2023-01-03T00:00:00.000+0000'}},  # 2 дня
                    {'fields': {'created': '2023-01-10T00:00:00.000+0000', 'resolutiondate': '2023-01-20T00:00:00.000+0000'}},  # 10 дней
                ]
            }
            mock_get.return_value = mock_response
            
            issues = get_jira_issues()
            task_1(issues)
            
            # ПРОВЕРЯЕМ: plt.hist вызван с правильными данными [2, 10]?
            mock_plt.hist.assert_called()
            hist_args = mock_plt.hist.call_args[0][0]  # Первый аргумент hist - массив данных
            self.assertEqual(len(hist_args), 2)  # 2 значения
            self.assertAlmostEqual(hist_args[0], 2.0)  # Первая задача: 2 дня
            self.assertAlmostEqual(hist_args[1], 10.0)  # Вторая задача: 10 дней

    def test_05_task4_top_users_correct_counting(self):
        """ТЕСТ 5: task_4() правильно считает ТОП пользователей (30 max)"""
        # Создаем тестовые задачи
        test_issues = [
            {'fields': {'assignee': {'displayName': 'User1'}, 'reporter': {'displayName': 'User2'}}},
            {'fields': {'assignee': {'displayName': 'User1'}, 'reporter': {'displayName': 'User1'}}},
            {'fields': {'assignee': None, 'reporter': {'displayName': 'User3'}}},
            {'fields': {'assignee': {'displayName': 'User2'}}},
        ]
        
        with patch('jira_analyzer.plt') as mock_plt:
            task_4(test_issues)
            
            # ПРОВЕРЯЕМ: plt.barh вызван с правильными данными?
            mock_plt.barh.assert_called()
            barh_args = mock_plt.barh.call_args[0]
            users = barh_args[0]  # Имена пользователей
            counts = barh_args[1]  # Количество задач
            
            self.assertIn('User1', users)  # User1 должен быть (3 задачи)
            self.assertIn('User2', users)  # User2 должен быть (2 задачи)
            self.assertIn('User3', users)  # User3 должен быть (1 задача)
            
            # User1: assignee(2) + reporter(1) = 3 задачи
            user1_idx = list(users).index('User1')
            self.assertEqual(counts[user1_idx], 3)

if __name__ == '__main__':
    unittest.main()
