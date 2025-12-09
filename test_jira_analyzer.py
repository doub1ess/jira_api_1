import unittest
from unittest.mock import patch, Mock
import sys
import os
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from jira_analyzer import calculate_time, get_jira_issues, task_1, task_3, task_4


class TestJiraAnalytics(unittest.TestCase):
    
    @patch('jira_analyzer.requests.get')
    @patch('jira_analyzer.MAX_RESULTS', 50)  # Мокаем MAX_RESULTS = 50
    def test_01_pagination_stops_correctly(self, mock_get):
        """ТЕСТ 1: Пагинация останавливается при неполной странице"""
        # Первый запрос: 50 задач (полная страница, MAX_RESULTS=50)
        response1 = Mock()
        response1.json.return_value = {
            'issues': [
                {'key': f'KAFKA-{i}', 
                'fields': {
                    'status': {'name': 'Closed'},
                    'created': '2023-01-01T00:00:00.000+0000',
                    'resolutiondate': '2023-01-05T00:00:00.000+0000'
                }} for i in range(50)
            ]
        }
    
        # Второй запрос: 30 задач (неполная страница - должен остановиться)
        response2 = Mock()
        response2.json.return_value = {
            'issues': [
                {'key': f'KAFKA-{i}', 
                'fields': {
                    'status': {'name': 'Closed'},
                    'created': '2023-01-01T00:00:00.000+0000',
                    'resolutiondate': '2023-01-05T00:00:00.000+0000'
                }} for i in range(50, 80)
            ]
        }
    
        # side_effect возвращает ответы по очереди
        mock_get.side_effect = [response1, response2]
    
        issues = get_jira_issues()
    
        # Проверяем: должно быть 80 задач и 2 запроса
        self.assertEqual(len(issues), 80, f"Ожидалось 80 задач, получено {len(issues)}")
        self.assertEqual(mock_get.call_count, 2, f"Ожидалось 2 запроса, сделано {mock_get.call_count}")
    
        # Проверяем параметры второго запроса (startAt должен быть 50)
        second_call_params = mock_get.call_args_list[1][1]['params']
        self.assertEqual(second_call_params['startAt'], 50)


    @patch('jira_analyzer.requests.get')
    def test_02_handles_connection_error(self, mock_get):
        """ТЕСТ 2: Обработка ошибок сети"""
        mock_get.side_effect = Exception("Connection timeout")
        
        issues = get_jira_issues()
        
        self.assertEqual(issues, [])
        self.assertTrue(mock_get.called)

    @patch('jira_analyzer.requests.get')
    def test_03_get_jira_issues_correct_jql(self, mock_get):
        """ТЕСТ 3: Правильный JQL запрос"""
        mock_response = Mock()
        mock_response.json.return_value = {'issues': []}
        mock_get.return_value = mock_response
        
        get_jira_issues()
        
        self.assertGreaterEqual(mock_get.call_count, 1)
        
        args, kwargs = mock_get.call_args_list[0]
        params = kwargs['params']
        
        self.assertIn("status in (Closed, Resolved)", params['jql'])
        self.assertIn("project=", params['jql'])

    @patch('jira_analyzer.requests.get')
    def test_04_task1_open_time_histogram_data(self, mock_get):
        """ТЕСТ 4: task_1() правильно собирает данные"""
        with patch('jira_analyzer.plt') as mock_plt:
            mock_response = Mock()
            mock_response.json.return_value = {
                'issues': [
                    {'fields': {
                        'created': '2023-01-01T00:00:00.000+0000', 
                        'resolutiondate': '2023-01-03T00:00:00.000+0000',
                        'status': {'name': 'Closed'}
                    }},
                    {'fields': {
                        'created': '2023-01-10T00:00:00.000+0000', 
                        'resolutiondate': '2023-01-20T00:00:00.000+0000',
                        'status': {'name': 'Closed'}
                    }},
                ]
            }
            mock_get.return_value = mock_response
            
            issues = get_jira_issues()
            task_1(issues)
            
            mock_plt.hist.assert_called()
            hist_args = mock_plt.hist.call_args[0][0]
            
            self.assertEqual(len(hist_args), 2)
            self.assertAlmostEqual(hist_args[0], 2.0)
            self.assertAlmostEqual(hist_args[1], 10.0)

    def test_05_task4_top_users_correct_counting(self):
        """ТЕСТ 5: task_4() правильно считает пользователей"""
        test_issues = [
            {'fields': {'assignee': {'displayName': 'User1'}, 'reporter': {'displayName': 'User2'}}},
            {'fields': {'assignee': {'displayName': 'User1'}, 'reporter': {'displayName': 'User1'}}},
            {'fields': {'assignee': None, 'reporter': {'displayName': 'User3'}}},
            {'fields': {'assignee': {'displayName': 'User2'}, 'reporter': None}},
        ]
        
        with patch('jira_analyzer.plt') as mock_plt:
            task_4(test_issues)
            
            mock_plt.barh.assert_called()
            barh_args = mock_plt.barh.call_args[0]
            users = barh_args[0]
            counts = barh_args[1]
            
            self.assertIn('User1', users)
            
            user1_idx = list(users).index('User1')
            self.assertEqual(counts[user1_idx], 3)


if __name__ == '__main__':
    unittest.main()
